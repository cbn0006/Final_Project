import os
import shutil
import json
import subprocess
import tempfile
import time
import csv
import logging
import re
import signal
import sys

# Symbols/functions to not include in my output csvs 
HARNESS_FUNCS: set[str] = {
    "waitForServerReady",
    "fetchFuzzCases",
    "resolveFn",
    "diffCoverage",
    "runFuzzerHarness",
    "walk",
    "raw",
    "targetModule.Api.isApiParamsSet",
    "<anon>",
}

class TsExtensionFuzzer:
    def __init__(self, rootPath, communicator, tmpDir, repoRoot, cleanup):
        self.rootPath = rootPath
        self.communicator = communicator
        self.currentDir = os.path.dirname(os.path.abspath(__file__))
        self.harnessSource = os.path.join(self.currentDir, "fuzzerHarness.template.ts")
        self.repoRoot = repoRoot
        if not os.path.isfile(self.harnessSource):
            raise FileNotFoundError(f"Cannot find harness at {self.harnessSource}")
        logging.debug(f"Found Harness file.")
        self.tmpDir = os.path.abspath(tmpDir)
        logging.info("TypeScript Fuzzer Initialized")
        self.workdir = None
        self.fuzzCopy = None
        self.vscodeProc = None
        self.vscodePath = "/usr/local/bin/code-gui"
        self.cleanup = cleanup

    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.closeFuzzSession()
        return False

    def _load_tsconfig(self, path: str) -> tuple[dict, str]:
        """Return (tsconfig_dict, outDir).  Accepts //-comments, /*…*/, trailing commas."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                txt = fh.read()
            # strip /* … */ comments
            txt = re.sub(r"/\*[\s\S]*?\*/", "", txt)
            # strip // … comments
            txt = re.sub(r"//.*", "", txt)
            # remove trailing commas
            txt = re.sub(r",\s*([}\]])", r"\1", txt)
            cfg = json.loads(txt) if txt.strip() else {}
        except Exception as e:
            logging.warning(f"Unable to parse tsconfig.json ({e}); assuming outDir='dist'")
            return {}, "dist"

        out_dir = cfg.get("compilerOptions", {}).get("outDir", "dist")
        return cfg, out_dir

    def prepareFuzzCopy(self, path):
        # This somehow fixes issues in the containerized version
        def ignore_bad_dirs(dir, files):
            ignore_list = []
            for f in files:
                if f in ['.git', '.vscode-server', 'node_modules', '__pycache__']:
                    ignore_list.append(f)
            return ignore_list
        workdir  = tempfile.mkdtemp(prefix="ext-fuzz-", dir=self.tmpDir)
        fuzzCopy = os.path.join(workdir, os.path.basename(self.rootPath))
        shutil.copytree(self.rootPath, fuzzCopy, symlinks=True, dirs_exist_ok=True, ignore=ignore_bad_dirs)
        logging.debug(f"Created temp working dir: {fuzzCopy}")

        srcDir     = os.path.join(fuzzCopy, "src")
        dstHarness = os.path.join(srcDir, "fuzzerHarness.ts")
        os.makedirs(srcDir, exist_ok=True)
        shutil.copy2(self.harnessSource, dstHarness)

        with open(self.harnessSource, "r", encoding="utf-8") as fh:
            tpl = fh.read()
        rel       = os.path.relpath(path, os.path.join(self.rootPath, "src"))
        modPath   = "./" + os.path.splitext(rel)[0].replace(os.sep, "/")

        custom_hooks = {
            "airflow-vscode-extension-main": "(targetModule as any).Api.isApiParamsSet = () => true;",
            "vscode-airflow-dag-viewer-main": "// no custom hook required for DAG viewer",
            "vscode-bentoml-main": "// Need to install python extension",
            "vscode-dvc-main": "// Nothing for now",
            "vscode-zenml-develop": "// Nothing for now"
        }

        injection_code = f"import * as targetModule from '{modPath}';\n"
        injection_code += custom_hooks.get(self.repoRoot, "// no special hooks")

        harnessTS = tpl.replace("PLACEHOLDER_IMPORT", injection_code)
        with open(dstHarness, "w", encoding="utf-8") as fh:
            fh.write(harnessTS)
        logging.debug("Injected module import into harness")

        pkgFile = os.path.join(fuzzCopy, "package.json")
        if not os.path.isfile(pkgFile):
            raise FileNotFoundError(f"package.json missing in {pkgFile}")
        pkg = json.load(open(pkgFile, "r", encoding="utf-8"))

        pkg["name"]        = pkg.get("name", "extension") + "-fuzz"
        pkg["displayName"] = pkg.get("displayName", pkg["name"]) + " (fuzzer)"
        pkg["version"]     = pkg.get("version", "0.0.0") + "-fuzz"
        act = pkg.get("activationEvents")
        if not isinstance(act, list):
            pkg["activationEvents"] = ["*"]
        elif "*" not in act:
            pkg["activationEvents"].insert(0, "*")
        if "build" in pkg.get("scripts", {}) and "yarn webpack" in pkg["scripts"]["build"]:
            logging.warning("Replacing 'yarn webpack' with 'npx webpack' in build script")
            pkg["scripts"]["build"] = pkg["scripts"]["build"].replace("yarn", "npx")
        json.dump(pkg, open(pkgFile, "w", encoding="utf-8"), indent=2)
        
        tsconfig_path = os.path.join(fuzzCopy, "tsconfig.json")
        tscfg, out_dir = self._load_tsconfig(tsconfig_path) if os.path.isfile(tsconfig_path) else ({}, "dist")

        compiler_opts = tscfg.get("compilerOptions", {})
        compiler_opts.update({
            "strict": False,
            "noImplicitAny": False,
            "forceConsistentCasingInFileNames": False,
            "allowUnreachableCode": True,
            "allowUnusedLabels": True,
            "noEmitOnError": False,
            "skipLibCheck": True
        })
        with open(tsconfig_path, "w", encoding="utf-8") as f:
            json.dump(tscfg, f, indent=2)
            logging.debug("Wrote patched tsconfig.json with lenient settings")

        main_js   = pkg.get("main", f"./{out_dir}/extension.js").lstrip("./\\")
        expected_main = os.path.join(out_dir, "extension.js").replace("\\", "/")

        webpack_cfg_path = os.path.join(fuzzCopy, "webpack.config.js")
        if not os.path.isfile(webpack_cfg_path):
            if main_js != expected_main:
                logging.warning("Webpack config missing and 'main' does not match outDir. Overwriting 'main' to point to %s", expected_main)
                pkg["main"] = f"./{expected_main}"
                main_js = expected_main
                with open(pkgFile, "w", encoding="utf-8") as f:
                    json.dump(pkg, f, indent=2)
                    logging.debug("Wrote updated package.json with corrected 'main' path.")

        base_js = os.path.basename(main_js)
        entry_ts = os.path.join(srcDir, base_js.replace(".js", ".ts"))

        if os.path.isfile(entry_ts):
            with open(entry_ts, "r", encoding="utf-8") as fh:
                src = fh.readlines()
            if "import './fuzzerHarness';" not in "".join(src):
                src.insert(0, "import './fuzzerHarness';\n")
                with open(entry_ts, "w", encoding="utf-8") as fh:
                    fh.writelines(src)
                logging.debug(f"Injected harness import into {entry_ts}")
        else:
            logging.warning(f"Could not find source entry file at {entry_ts}")

        harness_rel = os.path.relpath(dstHarness, fuzzCopy).replace("\\", "/")
        if "files" in tscfg and harness_rel not in tscfg["files"]:
            tscfg["files"].append(harness_rel)
            json.dump(tscfg, open(tsconfig_path, "w", encoding="utf-8"), indent=2)

        logging.debug("Finished patching copy; returning paths")
        return workdir, fuzzCopy

    def compileExtension(self, extPath):
        npm_cmd = "npm.cmd" if os.name == "nt" else "npm"

        if not os.path.isdir(extPath):
            raise FileNotFoundError(f"compileExtension: extPath not found: {extPath}")

        logging.info(f"Running '{npm_cmd} install' in {extPath}")
        subprocess.run([npm_cmd, "install", "--legacy-peer-deps"], cwd=extPath, check=True)

        logging.info(f"Running '{npm_cmd} run compile' in {extPath}")
        try:
            result = subprocess.run([npm_cmd, "run"], cwd=extPath, capture_output=True, text=True)

            if "compile" in result.stdout:
                subprocess.run([npm_cmd, "run", "compile"], cwd=extPath, check=True)
            elif "build" in result.stdout:
                subprocess.run([npm_cmd, "run", "build"], cwd=extPath, check=True)
            else:
                subprocess.run(["npx", "tsc", "--noEmit"], cwd=extPath, check=True)
        except subprocess.CalledProcessError as e:
            logging.warning(f"Compile completed with TypeScript errors: {e}. Proceeding anyway.")

    def startFuzzSession(self, initialTSFilePath):
        self.workdir, self.fuzzCopy = self.prepareFuzzCopy(initialTSFilePath)
        self.compileExtension(self.fuzzCopy)

        # Install any needed extensions once
        if self.repoRoot == "vscode-bentoml-main":
            ext_dir = os.path.join(self.workdir, "extensions")
            extensions_json = os.path.join(self.rootPath, ".vscode", "extensions.json")
            self.install_extensions(ext_dir, extensions_json)

        # Launch VS Code once
        self.vscodeProc = subprocess.Popen([
            self.vscodePath,
            "--new-window",
            "--extensionDevelopmentPath", self.fuzzCopy,
            "--extensions-dir", os.path.join(self.workdir, "extensions"),
            self.fuzzCopy
        ])

    def runSingleFile(self, cleanCSV, errorCSV, crashCSV):
        logging.info(f"Wating for fuzzing results")
        result = None
        for _ in range(120):
            time.sleep(1)
            resp = self.communicator.getLatestResult()
            if resp is not None:
                result = resp
                break

        def ensure_header(path_: str):
            if not os.path.exists(path_) or os.path.getsize(path_) == 0:
                with open(path_, "w", newline="", encoding="utf-8") as fh:
                    csv.writer(fh).writerow(["funcName", "args", "coverage", "error"])

        def write_rows(path_: str, items: list[dict]):
            if not items:
                return
            ensure_header(path_)
            with open(path_, "a", newline="", encoding="utf-8") as fh:
                w = csv.writer(fh)
                for it in items:
                    w.writerow([
                        it["funcName"],
                        json.dumps(it["args"]),
                        json.dumps(it["coverage"]),
                        it.get("error", "")
                    ])
        
        resp = self.communicator.resetLatestResult()

        def _prune_coverage(cov: dict):
            slim = {}
            for file_url, fn_list in cov.items():
                kept = [f for f in fn_list if f not in HARNESS_FUNCS]
                if kept:
                    slim[file_url] = kept
            return slim

        def _strip(item: dict):
            item = dict(item)
            item["coverage"] = _prune_coverage(item.get("coverage", {}))
            return item

        if result is not None:
            write_rows(cleanCSV, [_strip(x) for x in result.get("clean", [])])
            write_rows(errorCSV, [_strip(x) for x in result.get("errors", [])])
            if result.get("crash"):
                write_rows(crashCSV, [_strip(result["crash"])])
        else:
            write_rows(crashCSV, [{"funcName": "<process-crash>", "args": [], "coverage": {}, "error": ""}])
    
    def closeFuzzSession(self):
        if hasattr(self, "vscodeProc") and self.vscodeProc:
            self.vscodeProc.terminate()
            try:
                self.vscodeProc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.vscodeProc.kill()
            logging.info("VS Code closed.")
        if self.cleanup and hasattr(self, "workdir") and os.path.exists(self.workdir):
            shutil.rmtree(self.workdir)
            logging.info("Fuzz workdir cleaned up.")
        elif not self.cleanup:
            logging.info(f"Keeping temp workdir for inspection.")
    
    def install_extensions(self, ext_dir: str, extensions_json_path: str):
        vscode_cli = self.vscodePath

        if not os.path.isfile(extensions_json_path):
            logging.warning(f"No extensions.json found at {extensions_json_path}")
            return

        try:
            with open(extensions_json_path, "r", encoding="utf-8") as f:
                txt = f.read()
            txt = re.sub(r"//.*", "", txt)
            txt = re.sub(r",\s*([}\]])", r"\1", txt)
            data = json.loads(txt)
            recommendations = data.get("recommendations", [])
        except Exception as e:
            logging.error(f"Failed to read extensions.json: {e}")
            return

        if not isinstance(recommendations, list):
            logging.warning(f"No valid 'recommendations' found in {extensions_json_path}")
            return

        for ext_id in recommendations:
            try:
                subprocess.run([
                    vscode_cli,
                    "--install-extension", ext_id,
                    "--extensions-dir", ext_dir
                ], check=True)
                logging.info(f"Installed extension '{ext_id}' into fuzzing environment.")
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to install extension '{ext_id}': {e}")