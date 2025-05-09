# ./FilterMutants/mutantFilter.py
import logging
import os
import csv

class MutantFilter():
    """
    Takes in generated mutants for snippet or TypeScript files and makes sure no duplicates make it to be fuzzed.
    """
    def __init__(self, inputDir=None, singularSnippetCrashes=None, multiSnippetCrashes=None, snippetClean=None, cleanCSV=None, errorCSV=None, crashCSV=None):
        self.cleanDir = snippetClean
        self.inputDir = inputDir
        self.singularCrashesDir = singularSnippetCrashes
        self.multiCrashesDir = multiSnippetCrashes
        self.cleanCSV = cleanCSV
        self.errorCSV = errorCSV
        self.crashCSV = crashCSV
        logging.info("Mutant Filter Initialized")

    def filterSnippetMutants(self, potentialMuts):
        """
        Read CSVs and filter duplicates.
        """
        csvFiles = [
            os.path.join(self.singularCrashesDir, "crashes.csv"),
            os.path.join(self.multiCrashesDir, "multiCrashes.csv"),
            os.path.join(self.cleanDir, "clean.csv")
        ]
        alreadyTested = set()

        for filePath in csvFiles:
            if os.path.exists(filePath):
                logging.debug(f"Processing file for duplicate tests: {filePath}")
                with open(filePath, mode='r', newline='', encoding='utf-8') as csvfile:
                    reader = csv.reader(csvfile)
                    next(reader, None)
                    for row in reader:
                        if len(row) < 3:
                            continue
                        alreadyTested.add((str(row[0]), row[1], row[2]))
            else:
                logging.debug(f"File not found (skipping): {filePath}")

        filteredMutants = []
        for mutant in potentialMuts:
            line_no, originalLine, mutatedLine = mutant
            mutantTuple = (str(line_no), originalLine, mutatedLine)
            if mutantTuple not in alreadyTested:
                filteredMutants.append(mutant)
        
        logging.debug(f"{len(filteredMutants)} leftover after filtration.")
        return filteredMutants
    
    def filterTypeScriptMutants(self, potentialInputs):
        """
        Read CSVs and filter mutants.
        """
        tested = set()

        if self.cleanCSV and os.path.exists(self.cleanCSV):
            with open(self.cleanCSV, newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row:
                        continue
                    tested.add(tuple(row))
        
        if self.errorCSV and os.path.exists(self.errorCSV):
            with open(self.errorCSV, newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row:
                        continue
                    tested.add(tuple(row))

        if self.crashCSV and os.path.exists(self.crashCSV):
            with open(self.crashCSV, newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row:
                        continue
                    tested.add(tuple(row))

        filtered = []
        for funcName, argsList in potentialInputs:
            key = tuple([funcName] + argsList)
            if key in tested:
                logging.debug(f"Skipping already-tested input: {key}")
            else:
                filtered.append((funcName, argsList))

        logging.info(f"{len(filtered)} / {len(potentialInputs)} inputs remain after filtering")
        return filtered