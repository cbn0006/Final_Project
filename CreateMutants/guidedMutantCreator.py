# ./CreateMutants/guidedMutantCreator.py
import os
import csv
import random

class GuidedMutantCreator:
    """
    
    """
    def __init__(self, singularCrashesDir, multiCrashesDir):
        self.singularCrashesDir = singularCrashesDir
        self.multiCrashesDir = multiCrashesDir

    def guidedMutateSnippet(self, maxTests):
        crashRecords = self._loadCrashRecords()
        mutants = []
        for lineNo, originalLine, buggyLine in crashRecords:
            if len(mutants) >= maxTests:
                break
            newMutant = self._mutateLine(buggyLine)
            mutants.append((lineNo, originalLine, newMutant))
        return mutants

    def loadCrashRecords(self):
        records = []
        for crashDir in (self.singularCrashesDir, self.multiCrashesDir):
            if not os.path.isdir(crashDir):
                continue
            for fileName in os.listdir(crashDir):
                if not fileName.lower().endswith('.csv'):
                    continue
                filePath = os.path.join(crashDir, fileName)
                with open(filePath, newline='', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    next(reader, None)  # skip header
                    for row in reader:
                        if len(row) >= 3:
                            try:
                                lineNo = int(row[0])
                            except ValueError:
                                continue
                            records.append((lineNo, row[1], row[2]))
        return records

    def mutateLine(self, text):
        if not text:
            return text
        idx = random.randrange(len(text))
        if random.random() < 0.5:
            # delete a character
            return text[:idx] + text[idx+1:]
        else:
            # duplicate a character
            return text[:idx] + text[idx] + text[idx:]
