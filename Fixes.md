# Fixes Needed for Fuzzer

### Questions to Explore:
- What if a class has a constructor?
    - Use a regex to get constructor and dynamically instantiate the class?
- Is there a better way to fuzz than installing and compiling the dependencies and launching vs code?
- Is there a way to sift through functions that don't mean a lot to the funcionality of the program/
    - Make these "unimportant" functions weigh less when generating fuzz cases?
- Is there a more efficient way to feed the harness the fuzz cases?
    - Just paste a big list to be tested in the injected harness?
- Is there a way to learn the inputs that cause TypeErrors to avoid them altogether? (TypeError is the only error I am getting when the function is not clean)

### Areas of Improvement:
- Coverage:
    - Convert the compiled TS execution back to original source code. (There is a problem because the coverage tracker, tracks the execution of the compiled 'extension.js' file, so it does not translate directly back to the TypeScript files.)
- Discover Crashes:
    - At first, I thought I was creating crashes, but it was because I was causing Errors to "crash" the fuzzer.
- Dynamic Code Differences:
    - Be able to adjust to different function signatures better, adjust to constructors and non-constructors.
- Installation and Compilation Differences:
    - Be able to dynamically adjust to different package managers and where the program is compiled to.
- Time complexity:
    - This method is very time consuming and might be able to be sped up if you only have to install and compile the extension once. (I tried fixing this later in the project's lifecycle and it caused too many bugs, so I reverted. This might be the easiest to accomplish)
    - The Snippet Fuzzer is borderline unusable at its current state because of time consumption.
- Arguments:
    - Give the user more configurability
- Actual Guided Mutation Fuzzing:
    - I was never able to accomplish guided mutation fuzzing because the random mutation fuzzing wasn't yielding usable results.


## What Works
- End‑to‑end loop fuzzes every TypeScript file.
- CSV logging captures clean runs, errors, and coverage differences.
- Flask server and VS Code shut down cleanly on Ctrl-C.

## What’s Left
- Guided mutation logic.
- Source mapped coverage.
- Constructor creation.
- Performance tuning (build‑once, run‑many).

