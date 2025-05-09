# ./Guidance/guidanceEngine.py
import csv
import logging
import os

class GuidanceEngine:
    """
    Retrieves the paths of relevant TypeScript and Snippet files from directory.
    """
    def __init__(self, rootPath, backupDir, logDir):
        self.rootPath = rootPath
        logging.debug(f"Root Path: {rootPath}")
        self.backupDir = backupDir
        logging.debug(f"Backup Path {backupDir}")
        self.logDir = logDir
        logging.debug(f"Logs Path: {logDir}")
        logging.info("Initialized Guidance Engine.")

    def crawlDirectory(self):
        """
        Stores all TypeScript and CSV paths in respective CSV files.
        """
        logging.info("Starting crawling process...")

        srcDir = os.path.join(self.rootPath, "src")
        if not os.path.isdir(srcDir):
            logging.error(f"No 'src' directory found under {self.rootPath}")

        tsPaths = []
        for dirPath, _, files in os.walk(srcDir):
            for f in files:
                if f.endswith(".ts"):
                    tsPaths.append(os.path.join(dirPath, f))

        tsCsvPath = os.path.join(self.logDir, "TypeScriptPaths.csv")
        with open(tsCsvPath, mode='w', newline='', encoding='utf-8') as fh:
            writer = csv.writer(fh)
            writer.writerow(["Paths"])
            for p in tsPaths:
                writer.writerow([p])
        logging.debug(f"Saved {len(tsPaths)} TS paths to {tsCsvPath}")

        snippetPaths = []
        for dirPath, _, files in os.walk(self.rootPath):
            for f in files:
                if f.endswith(".code-snippets"):
                    snippetPaths.append(os.path.join(dirPath, f))

        snippetCsvPath = os.path.join(self.logDir, "snippetPaths.csv")
        with open(snippetCsvPath, mode='w', newline='', encoding='utf-8') as fh:
            writer = csv.writer(fh)
            writer.writerow(["Paths"])
            for p in snippetPaths:
                writer.writerow([p])
        logging.debug(f"Saved {len(snippetPaths)} snippet paths to {snippetCsvPath}")

    def getSnippetFilePaths(self, name, version, publisher):
        """
        Returns the snippet file paths for fuzzing.
        """
        snippetCsvPath = os.path.join(self.logDir, "snippetPaths.csv")
        snippetPaths = []

        if not os.path.exists(snippetCsvPath):
            logging.warning(f"{snippetCsvPath} does not exist.")
            return snippetPaths

        with open(snippetCsvPath, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                snippetPaths.append(row["Paths"])

        logging.info(f"Loaded {len(snippetPaths)} snippet paths from {snippetCsvPath}")

        activeExtDir = self.getActiveExtensionDir()
        if not activeExtDir:
            return []

        mappedPaths = []
        for path in snippetPaths:
            if not path.startswith(self.rootPath):
                logging.warning(f"Path {path} doesn't start with root path {self.rootPath}")
                continue

            relPath = os.path.relpath(path, self.rootPath)
            activePath = os.path.join(activeExtDir, f"{publisher}.{name}-{version}", relPath)
            mappedPaths.append(activePath)
            logging.debug(f"Mapped {path} -> {activePath}")

        return mappedPaths
    
    def getActiveExtensionDir(self):
        """
        Returns the path to the extension that VS Code is actually using.
        """
        home = os.path.expanduser("~")
        vscodeExtDir = os.path.join(home, ".vscode-server", "extensions")

        if not os.path.exists(vscodeExtDir):
            logging.warning(f"VS Code extensions directory not found at {vscodeExtDir}")
            return None

        logging.debug(f"VS Code extensions directory is {vscodeExtDir}")
        return vscodeExtDir

    def getTypeScriptPaths(self):
        """
        Returns the TypeScript file paths for fuzzing.
        """
        tsCsv = os.path.join(self.logDir, "TypeScriptPaths.csv")
        if not os.path.exists(tsCsv):
            logging.warning(f"{tsCsv} not found.") 
            return []

        paths = []
        with open(tsCsv, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                paths.append(row["Paths"])
        logging.info(f"Loaded {len(paths)} TS paths from {tsCsv}")
        return paths
