# ./SnippetFuzzer/snippetFuzzer.py
import logging
import subprocess
import re
import time
import os
import csv
import requests

class SnippetFuzzer():
    """
    Program that fuzzes desired snippet file via VS Code Extension.
    """
    def __init__(self, filteredMuts, snippetPath, backupDir, logDirPath):
        self.filteredMuts = filteredMuts
        self.snippetPath = snippetPath
        self.backupDir = backupDir
        self.logDirPath = logDirPath
        self.outputFile = None
        logging.info("Snippet Fuzzer Initialized")

    def applyMutations(self, idx):
        """
        Overwrites the active extension snippet file information with mutation.
        """
        logging.info(f"Applying mutation {idx} to {self.snippetPath}")

        mutation = self.filteredMuts[idx]
        line_number = int(mutation[0])
        original_line = mutation[1]
        mutated_line = mutation[2]
        logging.debug(f"Mutation: {mutation}")

        try:
            with open(self.snippetPath, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except FileNotFoundError:
            logging.error(f"File not found: {self.snippetPath}")
            return
        except Exception as e:
            logging.error(f"Error reading file: {e}")
            return

        if line_number < 1 or line_number > len(lines):
            logging.error(f"Line number {line_number} is out of range for file with {len(lines)} lines.")
            return

        current_line = lines[line_number].rstrip('\n')
        if current_line.strip() != original_line.strip():
            logging.warning(f"Sanity check failed at line {line_number}.\nExpected: {original_line}\nFound: {current_line}")

        lines[line_number] = mutated_line + '\n'

        try:
            with open(self.snippetPath, "w", encoding="utf-8") as f:
                f.writelines(lines)
            logging.info(f"Successfully applied mutation {idx + 1} to line {line_number}.")
        except Exception as e:
            logging.error(f"Failed to write mutated file: {e}")
        
    def convertSnippets(self):
        """
        Converts snippets to csv file for comparison to what is read in VS Code.
        """
        logging.debug("Extracting snippet pairs from code-snippets file.")
        snippets = []
        try:
            with open(self.snippetPath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            currentSnippet = None
            inBody = False
            bodyLinesContent = []
            bodyLineNums = []
            for i, line in enumerate(lines, 1):
                keyMatch = re.search(r'^\s*"(.+?)":\s*{', line)
                if keyMatch:
                    if currentSnippet is not None:
                        if inBody:
                            currentSnippet["body"] = "\n".join(bodyLinesContent)
                            currentSnippet["bodyLines"] = ",".join(map(str, bodyLineNums))
                            inBody = False
                            bodyLinesContent = []
                            bodyLineNums = []
                        snippets.append(currentSnippet)
                    currentSnippet = {
                        "key": keyMatch.group(1),
                        "keyLine": i,
                        "prefix": "",
                        "prefixLine": "",
                        "body": "",
                        "bodyLines": "",
                        "description": "",
                        "descriptionLines": ""
                    }
                    logging.debug(f"Snippet: {currentSnippet['key']} found.")
                if currentSnippet is not None:
                    prefixMatch = re.search(r'^\s*"prefix":\s*"(.+?)"', line)
                    if prefixMatch:
                        currentSnippet["prefix"] = prefixMatch.group(1)
                        currentSnippet["prefixLine"] = i
                    descMatch = re.search(r'^\s*"description":\s*"(.+?)"', line)
                    if descMatch:
                        currentSnippet["description"] = descMatch.group(1)
                        currentSnippet["descriptionLines"] = i
                    else:
                        currentSnippet["description"] = 'None'
                        currentSnippet["descriptionLines"] = 'None'
                    if re.search(r'^\s*"body":\s*\[', line):
                        inBody = True
                        continue
                    if inBody:
                        if re.search(r'^\s*\]', line):
                            inBody = False
                            currentSnippet["body"] = "\n".join(bodyLinesContent)
                            currentSnippet["bodyLines"] = ",".join(map(str, bodyLineNums))
                            bodyLinesContent = []
                            bodyLineNums = []
                        else:
                            clean_line = line.strip().rstrip(',').strip('"')
                            bodyLinesContent.append(clean_line)
                            bodyLineNums.append(i)
            if currentSnippet is not None:
                if inBody:
                    currentSnippet["body"] = "\\n".join(bodyLinesContent)
                    currentSnippet["bodyLines"] = ",".join(map(str, bodyLineNums))
                snippets.append(currentSnippet)
            logging.info(f"Successfully parsed {len(snippets)} snippets into robust CSV records for testing.")
            return snippets
        except Exception as e:
            logging.error(f"Error parsing snippet file {self.snippetPath}: {e}")
            return []
        
    def writeSnippetPairs(self, snippetRecords):
        """
        Writes the snippet file information to CSV.
        If this is not present upon launch, the extension will not work.
        """
        filePath = os.path.join(self.logDirPath, "snippets.csv")
        header = ["key", "keyLine", "prefix", "prefixLine", "body", "bodyLines", "description", "descriptionLines"]
        try:
            with open(filePath, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=header)
                writer.writeheader()
                for record in snippetRecords:
                    writer.writerow(record)
            logging.info(f"Snippets CSV written to {filePath}")
        except Exception as e:
            logging.error(f"Failed to write snippets CSV: {e}")

    def testSnippets(self, snippets):
        """
        Write to CSV and launch custom extension.
        """
        self.writeSnippetPairs(snippets)
        process, status = self.launch_vs_code()
        if process:
            process.terminate()
            logging.info("VS Code process terminated after testing snippets.")
        return status
    
    def launch_vs_code(self):
        """
        Launches VS Code on working directory with snippets.csv and checks to see status of snippets.
        """
        outputDir = self.logDirPath

        try:
            vscodePath = r"/usr/bin/code"
            if not os.path.exists(vscodePath):
                logging.error(f"VS Code executable not found at {vscodePath}")
                return None, None
            
            logPath = os.path.relpath(outputDir, start=os.getcwd())
            process = subprocess.Popen([vscodePath, logPath])
            logging.info("VS Code launched successfully.")

            timeout = 300
            interval = 15
            waited = 0
            snippetStatus = None
            
            while waited < timeout:
                try:
                    response = requests.get("http://127.0.0.1:5000/latest")
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("result") is not None:
                            snippetStatus = data["result"]
                            logging.info("Received response from extension via HTTP.")
                            break
                except Exception as e:
                    logging.error(f"Error while polling for extension result: {e}")
                time.sleep(interval)
                waited += interval

            if snippetStatus is None:
                logging.error("No response received from extension within timeout period.")
            return process, snippetStatus
        except Exception as e:
            logging.error(f"Failed to launch VS Code: {e}")
            return None, None
        
    def loadCSVSnippets(self):
        """
        Simple load function.
        """
        snippetCSVPath = os.path.join(self.logDirPath, "snippets.csv")
        snippets = []
        try:
            with open(snippetCSVPath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    snippets.append(row)
            logging.info(f"Loaded {len(snippets)} snippets from CSV.")
        except Exception as e:
            logging.error(f"Error reading CSV file {snippetCSVPath}: {e}")
        return snippets
        
    def compareResults(self, results):
        """
        Compare observed snippet behavior with normal snippet behavior.
        """
        logging.info("Comparing response from extension.")

        snippetCSV = self.loadCSVSnippets()
        if not snippetCSV:
            logging.error("No CSV records available for comparison.")
            return None
        
        output_string = self.convertResultsToString(results)
        logging.debug(output_string)

        matched, unmatched = [], []

        for snippet in snippetCSV:
            snippet_string = self.convertCSVToString(snippet)

            logging.debug(snippet_string)
            
            if snippet_string and snippet_string in output_string:
                logging.info(f"[MATCH] {snippet['key']} found in output.")
                matched.append(snippet['key'])
            else:
                logging.warning(f"[MISS] {snippet['key']} not found in output.")
                unmatched.append(snippet['key'])

        logging.info(f"\n=== Summary ===\nMatched: {len(matched)}\nUnmatched: {len(unmatched)}\n")
        return {
            "matched": matched,
            "unmatched": unmatched,
            "total": len(snippetCSV)
        }
        
    def convertResultsToString(self, results):
        """
        To perform proper comparison, must compare two strings.
        """
        try:
            raw_text = results.get("snippetResults", {}).get("allText", "")
            clean_text = raw_text.replace('\r\n', '\n').replace('\r', '\n').strip()
            clean_text = re.sub(r'[ \t]+', ' ', clean_text)
            return clean_text
        except Exception as e:
            logging.error(f"Failed to convert results to string: {e}")
            return ""

    def convertCSVToString(self, snippetRow):
        """
        To perform proper comparison, must compare two strings.
        """
        try:
            raw_body = snippetRow.get("body", "")

            # Remove VS Code placeholders like ${1:task_id} → task_id
            clean_body = re.sub(r'\$\{\d+:([^}]+)\}', r'\1', raw_body)

            # Step 1: Convert double-backslashes (\\) → single-backslash (\)
            clean_body = clean_body.replace('\\\\', '\\')

            # Step 2: Remove unnecessary escaping from things like \} \] \"
            clean_body = clean_body.replace('\\"', '"').replace("\\'", "'")
            clean_body = re.sub(r'\\([}\]])', r'\1', clean_body)

            # Normalize newlines and spaces
            clean_body = clean_body.replace('\r\n', '\n').replace('\r', '\n').strip()
            clean_body = re.sub(r'[ \t]+', ' ', clean_body)

            return clean_body
        except Exception as e:
            logging.error(f"Failed to convert CSV snippet to string: {e}")
            return ""