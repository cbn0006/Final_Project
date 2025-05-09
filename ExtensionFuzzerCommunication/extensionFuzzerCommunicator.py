# ./ExtensionFuzzerCommunication/extensionFuzzerCommunication.py
from flask import Flask, request, jsonify
import threading
import logging
import requests
class ExtensionFuzzerCommunicator:
    """
    HTTP server so harness can retrieve information and send results back to python scripts.
    """
    def __init__(self, host='127.0.0.1', port=5000):
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.latestTestResult = None
        self.setupRoutes()
        self.testQueue = None

    def setupRoutes(self):
        """
        Various routes used by Extension to communicate with python scripts.
        """
        # Extension reports data to python.
        @self.app.route('/report', methods=['POST'])
        def report():
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No JSON payload provided.'}), 400

            self.latestTestResult = data
            logging.info(f"Received test result: {data}")
            return jsonify({'status': 'received'}), 200
        
        # Call to keep retrieving the latest info from extension
        @self.app.route('/latest', methods=['GET'])
        def latest():
            return jsonify({"result": self.latestTestResult})
        
        # Reset so latest can be waited on again
        @self.app.route('/reset', methods=['POST'])
        def reset():
            self.latestTestResult = None
            logging.info("Extension test result reset.")
            return jsonify({'status': 'reset'}), 200
        
        # Allow python to set tests generated
        @self.app.route('/setTests', methods=['POST'])
        def set_tests():
            data = request.get_json()
            if not isinstance(data, list):
                return jsonify({'error':'expected JSON array'}), 400
            self.testQueue = data
            logging.info(f"Test queue set: {len(data)} cases")
            return jsonify({'status':'ok'}), 200

        # Allow harness to retrieve tests
        @self.app.route('/tests', methods=['GET'])
        def get_tests():
            return jsonify(self.testQueue), 200
        
        # Check to see if server is online.
        @self.app.route("/ping")
        def ping():
            return "OK", 200
        
        @self.app.route('/shutdown', methods=['POST'])
        def _shutdown():
            func = request.environ.get('werkzeug.server.shutdown')
            if func is None:                      # <‑‑ don’t raise, just return OK
                return jsonify({'status': 'not running with Werkzeug'}), 200
            func()
            return jsonify({'status': 'shutting down'}), 200

    # Run
    def run(self):
        self._thread = threading.Thread(
            target=self.app.run,
            kwargs={
                'host': self.host,
                'port': self.port,
                'debug': False,
                'use_reloader': False
            },
            daemon=True,
        )
        self._thread.start()
        print(f"HTTP server is running on http://{self.host}:{self.port}")
    
    def stop(self):
        try:
            requests.post(f"http://{self.host}:{self.port}/shutdown", timeout=2)
        except requests.RequestException:
            pass
        if getattr(self, "_thread", None):
            self._thread.join(timeout=5)

    """
    All 3 methods below are self-explanatory by intuition and function names.
    """

    def getLatestResult(self):
        return self.latestTestResult
    
    def resetLatestResult(self):
        try:
            response = requests.post(f"http://{self.host}:{self.port}/reset")
            if response.status_code == 200:
                logging.debug("Successfully reset test result on server.")
            else:
                logging.warning("Failed to reset test result on server.")
        except Exception as e:
            logging.error(f"Error resetting test result: {e}")

    def setTestQueue(self, cases):
        self.testQueue = cases