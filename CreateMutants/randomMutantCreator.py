# ./CreateMutants/randomMutantCreator.py
import logging
import random
import re
import string

class RandomMutantCreator():
    """
    Randomly creates mutations for snippet files and randomly mutates inputs for TypeScript functions.
    This is where the TypeScript function signatures are parsed as well.
    """

    # Keywords to watch out for
    TS_KEYWORDS = {
        "if", "for", "while", "do", "switch", "try", "catch", "finally", "return",
        "break", "continue", "new", "var", "let", "const", "function", "class",
        "export", "import", "extends", "implements", "interface", "package",
        "private", "protected", "public", "static", "yield", "await", "async", "constructor"
    }

    STRING_CHARS = string.ascii_letters + string.digits + string.punctuation
    def randAscii(self, n = 8):
        return '"' + "".join(random.choice(RandomMutantCreator.STRING_CHARS) for _ in range(n)) + '"'
    
    # Regexes for functions, classes, methods, and parameters. (This will probably need work as you find edge cases.)
    FUNC_RE = re.compile(
        r"""
        ^\s*
        export\s+
        (?P<modifiers>(?:(?:async)\s+)*)?
        function\s+
        (?P<name>[A-Za-z_]\w*)
        \((?P<params>[^\)]*)\)
        (?:\s*:\s*[^{]+)?
        \s*{
        """,
        re.M | re.X
    )
    CLASS_RE = re.compile(
        r"""
        export\s+class\s+
        (?P<cls>[A-Za-z_]\w*)
        (?:\s+extends\s+[^{\s]+)?
        (?:\s+implements\s+[^{\s]+)?
        \s*{
        """,
        re.M | re.X
    )
    METHOD_RE = re.compile(
        r"""
        ^\s*
        (?P<modifiers>(?:(?:public|protected|private|static|async)\s+)*)
        (?P<name>[A-Za-z_]\w*)\s*
        \((?P<params>[^\)]*)\)
        (?:\s*:\s*[^{]+)?
        \s*{
        """,
        re.M | re.X
    )
    PARAM_RE = re.compile(r"(\.\.\.)?(\w+)(\?)?\s*(?::\s*([^=]+))?")

    def __init__(self, filePath):
        self.filePath = filePath
        logging.info("Random Mutant Creator Initialized")
            
    def randomlyMutateSnippet(self, numMutants):
        """
        Randomly chooses line in snippet file and randomly mutates it.
        """
        filename = self.filePath.split("\\")[-1]
        logging.info(f"Attempting to create {numMutants} mutations for {filename}")
        mutants = []
        with open(self.filePath, 'r') as f:
            lines = f.readlines()

        totalLines = len(lines)

        for _ in range(numMutants):
            while True:
                line_no = random.randint(0, totalLines - 1)
                originalLine = lines[line_no].rstrip('\n')

                if not originalLine:
                    continue

                mutatedLine = []
                mutationCount = 0
                i = 0

                while i < len(originalLine):
                    char = originalLine[i]
                    roll = random.random()

                    if roll < 0.025:
                        insertChar = chr(random.randint(32, 126))
                        mutatedLine.append(insertChar)
                        mutatedLine.append(char)
                        mutationCount += 1
                        i += 1
                    elif roll < 0.05:
                        mutationCount += 1
                        i += 1
                    elif roll < 0.075:
                        replaceChar = chr(random.randint(32, 126))
                        mutatedLine.append(replaceChar)
                        mutationCount += 1
                        i += 1
                    else:
                        mutatedLine.append(char)
                        i += 1

                if mutationCount == 0:
                    mutationType = random.choice(['insert', 'delete', 'replace'])
                    pos = random.randint(0, len(originalLine) - 1)
                    mutatedLine = list(originalLine)

                    if mutationType == 'insert':
                        insertChar = chr(random.randint(32, 126))
                        mutatedLine.insert(pos, insertChar)
                    elif mutationType == 'delete':
                        mutatedLine.pop(pos)
                    elif mutationType == 'replace':
                        replaceChar = chr(random.randint(32, 126))
                        mutatedLine[pos] = replaceChar

                    mutationCount = 1
                    mutatedLine = ''.join(mutatedLine)
                else:
                    mutatedLine = ''.join(mutatedLine)

                mutants.append((line_no, originalLine, mutatedLine))
                break
        
        logging.debug(f"Mutants Created: {mutants}")
        filename = self.filePath.split("\\")[-1]
        logging.info(f"Created {len(mutants)} mutations for {filename}")
        return mutants
    
    def splitParams(self, paramStr):
        """
        Split the parameters in function signature and return them with form: (name, type, optional)
        """
        out = []
        for p in paramStr.split(","):
            p = p.strip()
            if not p:
                continue
            m = self.PARAM_RE.match(p)
            if not m:
                continue
            name = m.group(2)
            opt  = bool(m.group(3))
            typ  = (m.group(4) or "any").strip()
            out.append((name, typ, opt))
        return out

    def canonicalType(self, typ):
        """
        Cleanup and get type.
        """
        typ = typ.split("|", 1)[0]
        typ = re.sub(r"<.*?>", "", typ)
        return typ.strip().lower()

    def extractSignatures(self, src):
        """
        Parses function signatures in TypeScript files.
        Gets class name if there is one and creates signature type ([modifiers], {className}.{methodName}, (parameters)).
        If no class Name or function outside of class name, also adds ([modifiers], {funcName}, (parameters)) to signatures.
        """
        logging.info(f"Extracting functions to fuzz.")
        signatures = []

        for cls_m in self.CLASS_RE.finditer(src):
            clsName = cls_m.group("cls")
            logging.debug(f"Class: {clsName} found.")
            start = cls_m.end()
            depth = 1
            i = start
            classBody = []

            while i < len(src) and depth > 0:
                ch = src[i]
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                classBody.append(ch)
                i += 1

            classSrc = ''.join(classBody)
            lines = classSrc.splitlines()

            for line in lines:
                m = self.METHOD_RE.match(line)
                if m:
                    methodName = m.group("name")
                    if methodName in self.TS_KEYWORDS:
                        continue
                    
                    modifiersStr = m.group("modifiers").strip()
                    modifiers = modifiersStr.split() if modifiersStr else []
                        
                    params = self.splitParams(m.group("params"))
                    signatures.append((modifiers, f"{clsName}.{methodName}", params))
        
        for m in self.FUNC_RE.finditer(src):
            funcName = m.group("name")
            if funcName in self.TS_KEYWORDS:
                continue

            modifiersStr = (m.group("modifiers") or "").strip()
            modifiers = modifiersStr.split() if modifiersStr else []

            params = self.splitParams(m.group("params"))
            signatures.append((modifiers, funcName, params))

        logging.debug(f"Function signatures found: {signatures}")
        return signatures
    
    def randomlyCreateInputs(self, max_cases):
        """
        Main function for TypeScript input generation.
        Calls all other functions to parse the TypeScript and generate inputs.
        """
        src = open(self.filePath, encoding="utf-8").read()
        signatures = self.extractSignatures(src)
        if not signatures:
            logging.warning("No callable signatures found in %s", self.filePath)
            return []

        rng   = random.Random()
        seen  = set()
        cases = []

        while len(cases) < max_cases:
            modifiers, fn, params = rng.choice(signatures)
            args = [random.choice(self.valuesFor(t, opt)) for _, t, opt in params]
            key = (tuple(modifiers), fn, tuple(args))
            if key in seen:
                continue
            seen.add(key)
            cases.append((modifiers, fn, args))

        logging.debug("Mutated inputs: %s", cases)
        logging.info("Created %d inputs.", len(cases))
        return cases
    
    def valuesFor(self, typ, is_opt):
        """
        Helper function that just takes in parameter information and generates a random parameter.
        """
        def randString():
            length = random.randint(3, 20)
            return '"' + ''.join(random.choices(string.ascii_letters + string.digits, k=length)) + '"'

        def randNumber():
            return str(random.randint(0, 999))

        def randBoolean():
            return random.choice(["true", "false"])

        def randArray():
            length = random.randint(0, 25)
            contentType = random.choice(["string", "number"])
            if contentType == "string":
                return "[" + ", ".join(randString() for _ in range(length)) + "]"
            else:
                return "[" + ", ".join(randNumber() for _ in range(length)) + "]"

        def randObject():
            keyCount = random.randint(1, 5)
            obj = "{"
            for _ in range(keyCount):
                key = ''.join(random.choices(string.ascii_lowercase, k=random.randint(3, 8)))
                valueType = random.choice(["string", "number", "boolean", "null", "undefined"])
                if valueType == "string":
                    value = randString()
                elif valueType == "number":
                    value = randNumber()
                elif valueType == "boolean":
                    value = randBoolean()
                else:
                    value = valueType
                obj += f'"{key}": {value}, '
            obj = obj.rstrip(", ") + "}"
            return obj

        def randAny():
            choice = random.choice(["string", "number", "boolean", "array", "object", "null", "undefined"])
            if choice == "string":
                return randString()
            elif choice == "number":
                return randNumber()
            elif choice == "boolean":
                return randBoolean()
            elif choice == "array":
                return randArray()
            elif choice == "object":
                return randObject()
            else:
                return choice

        typ = self.canonicalType(typ)
        if is_opt:
            return [randAny()]

        if typ == "string":
            return [randString()]
        elif typ == "number":
            return [randNumber()]
        elif typ == "boolean":
            return [randBoolean()]
        elif "array" in typ:
            return [randArray()]
        elif typ == "object":
            return [randObject()]
        elif typ == "any":
            return [randAny()]
        else:
            return [randAny()]