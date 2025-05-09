# ./Logging/createLogsAndBackups.py
import os
import json
import logging
import shutil
import re
import csv

class DocumentCreator():
    """
    This is where all directories and routes for main program are instantiated and returned.
    """
    def __init__(self, extensionDir, repoRoot):
        self.extensionDir = extensionDir
        self.repoRoot = repoRoot
        self.logDir = None
        self.backupDir = None
        self.inputDir = None
        self.rootPath = None
        self.activeExtension = None
        self.singleCrashesPath = None
        self.multiCrashesPath = None
        self.cleanPath = None

    def getRootPath(self):
        """
        Returns path to root of the directory that contains the source code for the desired extension.
        Then it creates Logs, Backups, and Inputs directory.
        """
        if self.repoRoot:
            if not os.path.isdir(os.path.join(self.extensionDir, self.repoRoot)):
                print("Provided extension directory does not exist: %s", self.extensionDir)
                return None
            else:
                self.findValidExtensionRoot()
                self.createLogsAndBackups()
                subdirPath = os.path.join(self.extensionDir, self.repoRoot)
                split_path = subdirPath.split("\\")[-1]
                print(f"User provided directory \"{self.repoRoot}\"." + 
                              f' GuidanceEngine initalized with repository root "{split_path}"')
                return self.rootPath
        
        print("User did not provide a subdirectory. Finding subdirectory...")
        subdirs = [d for d in os.listdir(self.extensionDir) 
                   if os.path.isdir(os.path.join(self.extensionDir, d))]

        if not subdirs:
            print(f"No subdirectories found in extension directory: {self.extensionDir}")
            return None
        
        subdir = subdirs[0]
        self.findValidExtensionRoot()
        self.createLogsAndBackups()
        subdirPath = os.path.join(self.extensionDir, subdir)
        print(f"GuidanceEngine initialized with repository root: {subdir}")
        return self.rootPath
    
    def createLogsAndBackups(self):
        """
        Retrieve the necessary information for creation of logging, input, and backup directories and create them.
        """
        name, publisher = self.getExtensionInfo()
        
        if not name or not publisher:
            print("Could not create log/backup directories — extension info missing.")
            return
        
        folderName = f"{name} by {publisher}"
        
        scriptRoot = os.path.dirname(os.path.abspath(__file__))
        
        logsPath = os.path.join(scriptRoot, "Logs", folderName)
        self.logDir = logsPath
        backupsPath = os.path.join(scriptRoot, "Backups", folderName)
        self.backupDir = backupsPath
        inputPath = os.path.join(scriptRoot, "Inputs", folderName)
        self.inputDir = inputPath

        try:
            os.makedirs(logsPath, exist_ok=True)
            print(f"Created/Verified logs directory: {logsPath}")
            
            os.makedirs(backupsPath, exist_ok=True)
            print(f"Created/Verified backups directory: {backupsPath}")

            os.makedirs(inputPath, exist_ok=True)
            print(f"Created/Verified inputs directory: {inputPath}")
            
        except Exception as e:
            print(f"Failed to create log/backup directories: {e}")
    
    def getExtensionInfo(self):
        '''
        Just prints and returns displayName and publisher of extension.
        '''
        try:
            packageJsonPath = os.path.join(self.rootPath, "package.json")

            if not os.path.exists(packageJsonPath):
                print(f"package.json not found in the provided directory: {self.rootPath}")
                return

            with open(packageJsonPath, 'r', encoding='utf-8') as f:
                packageData = json.load(f)

            displayName = packageData.get("displayName", None)
            publisher = packageData.get("publisher", None)

            if not displayName or not publisher:
                print("displayName or publisher missing in package.json.")
                return
            print(f"\n{displayName} by {publisher}\n")

            return displayName, publisher

        except json.JSONDecodeError as e:
            print(f"Failed to parse package.json. Error: {e}")
        except Exception as e:
            print(f"An unexpected error occurred while capturing extension info: {e}")
    
    def findValidExtensionRoot(self):
        """
        Finds directory of package.json file that contains the information needed to actually compile and create the
        extension. This is supposed to be the greatest common ancestor of all relevant TypeScript code.
        """
        searchRoot = os.path.join(self.extensionDir, self.repoRoot) if self.repoRoot else self.extensionDir

        for dirpath, _, filenames in os.walk(searchRoot):
            if "package.json" in filenames:
                pkgPath = os.path.join(dirpath, "package.json")
                try:
                    with open(pkgPath, 'r', encoding='utf-8') as f:
                        packageData = json.load(f)

                    # Check required keys
                    required_keys = ["name", "displayName", "publisher", "version"]
                    if all(k in packageData for k in required_keys):
                        self.rootPath = dirpath
                        print(f"Valid extension found: {packageData['displayName']} by {packageData['publisher']}")
                        return dirpath

                except json.JSONDecodeError as e:
                    print(f"JSON decode error in {pkgPath}: {e}")
                except Exception as e:
                    print(f"Error reading {pkgPath}: {e}")

        print("No valid extension with all required fields found.")
        return None
    
    def getDirectories(self):
        """
        Self-explanatory
        """
        return self.logDir, self.backupDir
    
    def getExtensionPathInfo(self):
        '''
        Returns (name, version, publisher) from package.json in self.rootPath.
        PLEASE note: displayName and name are two different things in package.json.
        '''
        if not self.rootPath:
            print("rootPath is not set. Cannot fetch extension metadata.")
            return None, None, None

        packageJsonPath = os.path.join(self.rootPath, "package.json")

        try:
            if not os.path.exists(packageJsonPath):
                print(f"package.json not found at: {packageJsonPath}")
                return None, None, None

            with open(packageJsonPath, 'r', encoding='utf-8') as f:
                packageData = json.load(f)

            name = packageData.get("name")
            version = packageData.get("version")
            publisher = packageData.get("publisher")

            if not name or not version or not publisher:
                print("Missing one or more required fields in package.json.")
                return None, None, None

            return name, version, publisher

        except json.JSONDecodeError as e:
            print(f"Failed to parse package.json: {e}")
        except Exception as e:
            print(f"Unexpected error reading package.json: {e}")

        return None, None, None
    
    '''
    Logging has been initialized after this point
    '''

    def createBackups(self, path):
        """
        Creates a backup of the snippet file for restoration at end of fuzzing loop.
        """
        logging.debug(f"Copying code-snippets file at {path} to {self.backupDir}")

        if not self.backupDir:
            logging.error("Backup directory is not set. Cannot create backup.")
            return

        if not os.path.exists(path):
            logging.error(f"Source snippet file does not exist at: {path}")
            return

        try:
            match = re.search(r'extensions[\\/](.+)', path)
            if not match:
                logging.error("Could not determine relative path from 'extensions\\'.")
                return

            relativePath = match.group(1)
            self.activeExtension = relativePath

            destPath = os.path.join(self.backupDir, self.activeExtension)

            os.makedirs(os.path.dirname(destPath), exist_ok=True)

            shutil.copy2(path, destPath)
            logging.debug(f"Backup created at {destPath}")
            return destPath

        except Exception as e:
            print(f"Failed to create backup: {e}")

    def createSnippetInputPath(self):
        """
        Creates CSVs for snippet output information.
        """
        if not self.inputDir or not self.activeExtension:
            logging.error("Input directory or activeExtension is not set. Cannot create snippet paths.")
            return None, None, None

        try:
            basePath = os.path.join(self.inputDir, self.activeExtension)
            self.multiCrashesPath = os.path.join(basePath, "Crashes", "Multi")
            self.singleCrashesPath = os.path.join(basePath, "Crashes", "Single")
            self.cleanPath = os.path.join(basePath, "Clean")

            os.makedirs(self.singleCrashesPath, exist_ok=True)
            os.makedirs(self.multiCrashesPath, exist_ok=True)
            os.makedirs(self.cleanPath, exist_ok=True)

            logging.debug(f"Created/verified base input path: {basePath}")
            logging.debug(f"Created/verified crashes path: {self.singleCrashesPath}")
            logging.debug(f"Created/verified crashes path: {self.multiCrashesPath}")
            logging.debug(f"Created/verified clean path: {self.cleanPath}")

            return basePath, self.singleCrashesPath, self.multiCrashesPath, self.cleanPath

        except Exception as e:
            logging.error(f"Failed to create snippet input directories: {e}")
            return None, None, None
        
    def restoreSnippets(self, snippetPath, snippetBackup):
        """
        Restores snippet file to original.
        """
        logging.debug(f"Restoring snippet file from {snippetBackup} to {snippetPath}")

        if not os.path.exists(snippetBackup):
            logging.error(f"Backup file does not exist at: {snippetBackup}")
            return

        try:
            shutil.copy2(snippetBackup, snippetPath)
            logging.info(f"Snippet file restored from backup at {snippetBackup}")
        except Exception as e:
            logging.error(f"Failed to restore snippet file: {e}")

    def writeSingle(self, x, muts):
        """
        Writes to singular snippet crash CSV.
        """
        crashFile = os.path.join(self.singleCrashesPath, "crashes.csv")
        fileExists = os.path.isfile(crashFile)

        with open(crashFile, mode='a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)

            if not fileExists:
                writer.writerow(["Line Num", "Original Line", "Mutated Line"])

            writer.writerow(muts[x])

    def writeClean(self, x, muts):
        """
        Writes to clean CSV.
        """
        cleanFile = os.path.join(self.cleanPath, "clean.csv")
        fileExists = os.path.isfile(cleanFile)

        with open(cleanFile, mode='a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            if not fileExists:
                writer.writerow(["Line Num", "Original Line", "Mutated Line"])
            writer.writerow(muts[x])

    def writeMulti(self, x, muts):
        """
        Writes to multiple snippet crash CSV.
        """
        multiFile = os.path.join(self.multiCrashesPath, "multiCrashes.csv")
        fileExists = os.path.isfile(multiFile)

        with open(multiFile, mode='a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            if not fileExists:
                writer.writerow(["Line Num", "Original Line", "Mutated Line"])
            writer.writerow(muts[x])

    def createTypeScriptInputPath(self, path):
        """
        Creates a directory named after the TypeScript file being fuzzed and initializes
        all necessary CSVs for writing results of fuzzing.
        """
        if not self.inputDir or not self.rootPath:
            logging.error("Input directory or rootPath not set. Cannot create TS input path.")
            return None, None, None

        relPath = os.path.relpath(path, self.rootPath)
        relDir = os.path.splitext(relPath)[0]

        basePath = os.path.join(self.inputDir, relDir)
        os.makedirs(basePath, exist_ok=True)

        cleanCsvPath   = os.path.join(basePath, "clean.csv")
        errorsCsvPath = os.path.join(basePath, "errors.csv")
        crashesCsvPath = os.path.join(basePath, "crashes.csv")

        for csvPath in (cleanCsvPath, errorsCsvPath, crashesCsvPath):
            if not os.path.exists(csvPath):
                with open(csvPath, "w", encoding="utf-8") as fh:
                    pass

        logging.debug(f"Created TS input folder at {basePath} with clean.csv, errors.csv, and crashes.csv")
        return basePath, cleanCsvPath, errorsCsvPath, crashesCsvPath