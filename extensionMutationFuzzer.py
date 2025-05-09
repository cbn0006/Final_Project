# ./extensionMutationFuzzer.py
"""
Main program for running random and guided mutation fuzzing on VS Code Extensions.
"""
import argparse
import logging
import os
import sys
import signal
import atexit
from Guidance.guidanceEngine import GuidanceEngine
from Logging.createLogsAndBackups import DocumentCreator
from CreateMutants.randomMutantCreator import RandomMutantCreator
from FilterMutants.mutantFilter import MutantFilter
from SnippetFuzzer.snippetFuzzer import SnippetFuzzer
from ExtensionFuzzerCommunication.extensionFuzzerCommunicator import ExtensionFuzzerCommunicator
from CreateMutants.guidedMutantCreator import GuidedMutantCreator
from FuzzingHarness.tsExtensionFuzzer import TsExtensionFuzzer

def setupLogging(logMode, logDir, logFileName):
    """
    Method to setup logging for the entire program. Can either be debug, info, or None.
    """
    logPath = os.path.join(logDir, logFileName)
    logFormat = "%(asctime)s - %(levelname)s - %(message)s"

    # Clear old handlers before setting new ones
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    if logMode == "debug":
        level = logging.DEBUG
    elif logMode == "info":
        level = logging.INFO
    else:
        logging.disable(logging.CRITICAL + 1)
        return

    # Setup both file and console logging
    logging.basicConfig(
        level=level,
        format=logFormat,
        handlers=[
            logging.FileHandler(logPath, mode='w', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

    logging.info(f"Logging initialized for {logFileName if logFileName else 'fuzzing.log'}")

activeFuzzers: list["TsExtensionFuzzer"] = []
activeCommunicators: list[ExtensionFuzzerCommunicator] = []

def globalCleanup():
    for f in activeFuzzers:
        try:
            f.closeFuzzSession()
        except Exception:
            pass
    for c in activeCommunicators:
        try:
            c.stop()
        except Exception:
            pass
    activeFuzzers.clear()
    activeCommunicators.clear()

# run on normal interpreter exit
atexit.register(globalCleanup)

def sigHandler(signum, frame):
    globalCleanup()
    os._exit(128 + signum)

for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGQUIT):
    signal.signal(sig, sigHandler)

def main():
    """
    Main function for main program of this fuzzer.
    """
    # Setup command line arguments
    parser = argparse.ArgumentParser(description="Mutation Guided and Random Fuzzing Application")
    
    parser.add_argument(
        '--max_iters', 
        type=int, 
        required=False, 
        default=10,
        help='Number of crashes desired'
    )
    parser.add_argument(
        '--max_tests',
        type=int,
        required=False,
        default=128,
        help='Max number of mutations performed per iteration.'
    )
    parser.add_argument(
        '--logging', 
        type=str, 
        choices=['info', 'debug'], 
        default=None,
        help='Logging level (info, debug). Default is None.'
    )
    parser.add_argument(
        '--repo_root', 
        type=str, 
        required=False, 
        default=None,
        help='Name your Extension\'s root directory. Used in case there are multiple subdirectories of the Extension directory.'
    )
    parser.add_argument(
        '--file_options',
        type=str,
        choices=['ts','snippet'],
        default=None,
        help='Desired file type to be fuzzed.'
    )
    parser.add_argument(
        '--fuzz_type',
        type=str,
        choices=['random', 'guided'],
        default='random',
        help='Set desired fuzzing type.'
    )
    parser.add_argument(
        '--cleanup',
        dest='cleanup',
        action='store_true',
        help='Remove the temporary work-dir when the run finishes (default).'
    )
    parser.add_argument(
        '--no-cleanup',
        dest='cleanup',
        action='store_false',
        help='Keep the temporary work-dir for inspection.'
    )
    parser.set_defaults(cleanup=True)
    
    args = parser.parse_args()

    # Instantiate HTTP Server for Extension to be able to communicate with everything else
    communicator = ExtensionFuzzerCommunicator(host='127.0.0.1', port=5000)
    communicator.run()
    activeCommunicators.append(communicator)

    # Get current directory and directory where Extension repository roots are supposed to be located
    currentDir = os.path.dirname(os.path.abspath(__file__))
    extensionDir = os.path.join(currentDir, "Extension")

    # Create document creator, get root path, logs directory path, and backups directory path
    documentCreator = DocumentCreator(extensionDir, args.repo_root)
    rootPath = documentCreator.getRootPath()
    logDirPath, backupDirPath = documentCreator.getDirectories()

    # Get name and version for finding extension path in active VS Code extensions
    name, version, publisher = documentCreator.getExtensionPathInfo()

    # Get max iterations
    maxIters = args.max_iters

    # Loop through the repo iter amount of times performing guided/random mutation fuzzing
    for iters in range(1,maxIters + 1):
        logFile = f"iteration{iters}.log"
        setupLogging(args.logging, logDirPath, logFile)

        # Initialize the Guidance Engine
        guidanceEngine = GuidanceEngine(
                            rootPath=rootPath,
                            backupDir=backupDirPath,
                            logDir=logDirPath
                        )
        
        print(f"\n--------------------------------------------------\n\nIteration {iters}/{maxIters} starting...\n")
        logging.info(f"Iteration {iters}/{maxIters} started")

        # Crawls repo directory to create 2 csvs with paths to all .ts files and all .code-snippets files
        guidanceEngine.crawlDirectory()

        if not args.file_options or args.file_options == "snippet":
            # Return list of snippet file paths
            snippetFilePaths = guidanceEngine.getSnippetFilePaths(name, version, publisher)

            if len(snippetFilePaths) == 0:
                logging.info("There are 0 detected snippet files. Moving on.")
            elif len(snippetFilePaths) > 0:
                # Fuzz snippet files logic
                for snippetPath in snippetFilePaths:
                    # Create a backup for the snippet file and return a path to find this individual backup at
                    snippetBackupPath = documentCreator.createBackups(snippetPath)

                    # Create input directories for this extension
                    inputSnippetDir, singularSnippetCrashes, multiSnippetCrashes, snippetClean = documentCreator.createSnippetInputPath()
                    
                    # If no known buggy inputs, run random creator. Else, run guided creator.
                    # This needs to be handled by the user manually for now at least.
                    mutantCreator = None
                    if args.fuzz_type == 'random':
                        mutantCreator = RandomMutantCreator(filePath=snippetPath)
                    else:
                        mutantCreator = GuidedMutantCreator(singularSnippetCrashes, multiSnippetCrashes)

                    # Initialize filter
                    mutantFilter = MutantFilter(inputDir=inputSnippetDir,
                                                singularSnippetCrashes=singularSnippetCrashes,
                                                multiSnippetCrashes=multiSnippetCrashes, 
                                                snippetClean=snippetClean
                                                )

                    # Create args.max_test Mutants
                    mutants = None
                    if args.fuzz_type == 'random':
                        mutants = mutantCreator.randomlyMutateSnippet(args.max_tests)
                    else:
                        mutants = mutantCreator.guidedMutateSnippet(args.max_tests)

                    # Filter Mutants
                    filteredMuts = mutantFilter.filterSnippetMutants(mutants)
                    
                    # Initialize Snippet Fuzzer
                    snippetFuzz = SnippetFuzzer(filteredMuts, snippetPath, backupDirPath, logDirPath)

                    # For every mutation created in filteredMuts, get snippet pairs,
                    # test to make sure the file is not corrupted, apply mutations to the snippet file,
                    # get new snippet pairs, and test to see if behavior changed
                    for x in range(len(filteredMuts)):
                        # Uncomment below if there is believed to be a bug in the default snippets file
                        '''
                        # Convert the snippets to a list
                        cleanSnippets = snippetFuzz.convertSnippets()

                        # Write snippets to CSV, launch extension and get output
                        snippetFuzz.testSnippets(cleanSnippets)

                        # Get snippets fuzzing results from extension
                        extensionResults = communicator.getLatestResult()

                        # Compare extension's results to expected
                        results = snippetFuzz.compareResults(extensionResults)

                        # Currently for bug fixing edge cases and program execution problems
                        if len(results["matched"]) != len(cleanSnippets):
                            logging.error(f"Length: {len(cleanSnippets)} does not equal expected length: {len(results["matched"])}")
                            # Maybe restore the file once I'm done bug fixing
                            exit()
                        '''
                        
                        # Apply mutations to snippet file
                        snippetFuzz.applyMutations(x)

                        # Reset the result to be able to run mutations
                        communicator.resetLatestResult()
                        
                        # Convert the snippets to a list
                        mutatedSnippets = snippetFuzz.convertSnippets()

                        # Write fuzzed snippets to CSV, launch extension and get output
                        snippetFuzz.testSnippets(mutatedSnippets)

                        # Get snippets fuzzing results from extension
                        mutatedResults = communicator.getLatestResult()

                        # See what snippets crashed if any
                        mutatedResults = snippetFuzz.compareResults(mutatedResults)
    
                        if len(mutatedResults["unmatched"]) > 1:
                            logging.debug(f"Snippet file does not work.")
                            documentCreator.writeMulti(x, filteredMuts)
                        elif len(mutatedResults["unmatched"]) == 1:
                            logging.debug(f"One snippet crashed.")
                            documentCreator.writeSingle(x, filteredMuts)
                        else:
                            logging.debug(f"Mutation did not crash snippets.")
                            documentCreator.writeClean(x, filteredMuts)

                        # Reset the result to loop back around
                        communicator.resetLatestResult()

                        # Restore snippets in active VS Code extensions with backup
                        documentCreator.restoreSnippets(snippetPath, snippetBackupPath)
        
        if not args.file_options or args.file_options == "ts":
            # Fuzz TypeScript files logic

            # Get TypeScript file paths
            typeScriptFilePaths = guidanceEngine.getTypeScriptPaths()

            if len(typeScriptFilePaths) == 0:
                logging.error("Typescript files not found")
            elif len(typeScriptFilePaths) > 0:
                # Currently, just start from the first path in the csv file. (WILL CHANGE LATER. MAYBE GIVE USER AN OPTION?!?!)

                for typeScriptFilePath in typeScriptFilePaths:
                    # Init fuzzer
                    with TsExtensionFuzzer(
                        rootPath = rootPath,
                        communicator = communicator,
                        tmpDir = backupDirPath,
                        repoRoot = args.repo_root,
                        cleanup = args.cleanup) as fuzzer:

                        activeFuzzers.append(fuzzer)
                        try:
                            fuzzer.startFuzzSession(typeScriptFilePath)
                            # Currently don't need to create backups

                            # Create inputs directories
                            inputTSDir, cleanCSV, errorCSV, crashCSV = documentCreator.createTypeScriptInputPath(typeScriptFilePath)

                            logging.info(f"Fuzzing TypeScript file at: {typeScriptFilePath}")

                            # Initialize Mutant Creator
                            mutantCreator = None
                            if args.fuzz_type == 'random':
                                mutantCreator = RandomMutantCreator(filePath=typeScriptFilePath)
                            else:
                                mutantCreator = GuidedMutantCreator(filePath=typeScriptFilePath)

                            # Initialize Mutant Filter
                            mutantFilter = MutantFilter(inputDir=inputTSDir,
                                                        cleanCSV=cleanCSV,
                                                        errorCSV=errorCSV,
                                                        crashCSV=crashCSV
                                                        )

                            # Decide what files/methods to fuzz and create inputs(Can make this more robust through building out guidance engine)
                            inputs = None
                            if args.fuzz_type == 'random':
                                inputs = mutantCreator.randomlyCreateInputs(args.max_tests)
                            else:
                                inputs = mutantCreator.guidedCreateInputs

                            if len(inputs) == 0:
                                logging.warning(f"Input creator could not find inputs to create. Skipping this TS file...")
                                continue

                            # Filter mutations
                            inputs = [(fn, args) for _, fn, args in inputs]
                            filteredInputs = mutantFilter.filterTypeScriptMutants(inputs)

                            # Put test cases in queue for harness to use
                            communicator.setTestQueue([{"funcName": fn, "args": args} for fn, args in filteredInputs])

                            # Fuzz the TypeScript File
                            fuzzer.runSingleFile(cleanCSV, errorCSV, crashCSV)
                
                        finally:
                            activeFuzzers.remove(fuzzer)

        logging.info(f"Iteration {iters} completed\n")

    # Create a script that performs calculations on logs and output information (Potentially)

if __name__ == "__main__":
    main()
