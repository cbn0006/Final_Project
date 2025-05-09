"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || function (mod) {
    if (mod && mod.__esModule) return mod;
    var result = {};
    if (mod != null) for (var k in mod) if (k !== "default" && Object.prototype.hasOwnProperty.call(mod, k)) __createBinding(result, mod, k);
    __setModuleDefault(result, mod);
    return result;
};
var __awaiter = (this && this.__awaiter) || function (thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
};
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.deactivate = exports.activate = void 0;
const vscode = __importStar(require("vscode"));
const fs = __importStar(require("fs"));
const path = __importStar(require("path"));
const sync_1 = require("csv-parse/sync");
const node_fetch_1 = __importDefault(require("node-fetch"));
const verbose = true;
function sendTestResult(result) {
    return __awaiter(this, void 0, void 0, function* () {
        try {
            const response = yield (0, node_fetch_1.default)("http://127.0.0.1:5000/report", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(result)
            });
            const data = yield response.json();
            console.log("Server response:", data);
            return data;
        }
        catch (error) {
            vscode.window.showErrorMessage("Failed to report test result: " + error);
            return null;
        }
    });
}
function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}
function waitForDocumentChange(document, condition, timeoutMs = 3000) {
    return new Promise(resolve => {
        const subscription = vscode.workspace.onDidChangeTextDocument(e => {
            if (e.document === document && condition(e.document)) {
                subscription.dispose();
                resolve();
            }
        });
        setTimeout(() => {
            subscription.dispose();
            console.warn("Document change condition not met within timeout.");
            resolve(); // Even if timeout, resolve so the flow continues.
        }, timeoutMs);
    });
}
function moveCursorToEOF(editor) {
    return __awaiter(this, void 0, void 0, function* () {
        const lastLine = editor.document.lineAt(editor.document.lineCount - 1);
        const eofPosition = lastLine.range.end;
        editor.selection = new vscode.Selection(eofPosition, eofPosition);
    });
}
function closeVSCodeWithoutSaving() {
    return __awaiter(this, void 0, void 0, function* () {
        while (vscode.window.visibleTextEditors.length > 0) {
            yield vscode.commands.executeCommand('workbench.action.revertAndCloseActiveEditor');
            yield delay(500);
        }
        yield vscode.commands.executeCommand('workbench.action.closeWindow');
    });
}
function activate(context) {
    console.log('Snippet Tester extension activated.');
    let disposable = vscode.commands.registerCommand('snippetTester.testAllSnippets', () => __awaiter(this, void 0, void 0, function* () {
        const logMessages = [];
        const snippetResults = [];
        const logVerbose = (msg) => {
            console.log(msg);
            if (verbose)
                logMessages.push(msg);
        };
        let snippetsCsvPath;
        if (vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length > 0) {
            snippetsCsvPath = path.join(vscode.workspace.workspaceFolders[0].uri.fsPath, 'snippets.csv');
        }
        else {
            snippetsCsvPath = path.join(process.cwd(), 'snippets.csv');
        }
        if (!fs.existsSync(snippetsCsvPath)) {
            vscode.window.showErrorMessage(`Snippets CSV file not found at ${snippetsCsvPath}`);
            return;
        }
        let csvContent;
        try {
            csvContent = fs.readFileSync(snippetsCsvPath, 'utf8');
        }
        catch (err) {
            vscode.window.showErrorMessage(`Failed to read snippets CSV file: ${err}`);
            return;
        }
        // Parse CSV into objects for each snippet.
        let snippetRecords = [];
        try {
            snippetRecords = (0, sync_1.parse)(csvContent, {
                columns: true,
                skip_empty_lines: true
            });
        }
        catch (error) {
            vscode.window.showErrorMessage(`Error parsing CSV file: ${error}`);
            return;
        }
        // Open an untitled Python document.
        const document = yield vscode.workspace.openTextDocument({ content: '', language: 'python' });
        const editor = yield vscode.window.showTextDocument(document);
        // Iterate over all snippet records.
        for (let i = 0; i < snippetRecords.length; i++) {
            const record = snippetRecords[i];
            const key = record["key"];
            const prefix = record["prefix"];
            logVerbose(`Testing snippet '${key}' with prefix "${prefix}"`);
            // Ensure the cursor is at the end of the document.
            const prevLineCount = editor.document.lineCount;
            const lastLine = editor.document.lineAt(prevLineCount - 1);
            const eofPosition = lastLine.range.end;
            editor.selection = new vscode.Selection(eofPosition, eofPosition);
            // Insert a new line if not the first snippet.
            if (i !== 0) {
                yield editor.edit(editBuilder => {
                    editBuilder.insert(eofPosition, '\n');
                });
                // Wait for the document's line count to increase.
                yield waitForDocumentChange(editor.document, doc => doc.lineCount > prevLineCount);
            }
            // Capture baseline content before typing the prefix.
            const baselineContent = editor.document.getText();
            // Type the snippet prefix.
            yield vscode.commands.executeCommand('type', { text: prefix });
            // Wait until the new text appears in the document.
            yield waitForDocumentChange(editor.document, doc => doc.getText().includes(prefix), 3000);
            // Trigger code suggestions.
            yield vscode.commands.executeCommand('editor.action.triggerSuggest');
            // Optional: wait a brief moment for the suggestions to appear.
            yield delay(500);
            // Capture the document's content before accepting the suggestion.
            const beforeAcceptContent = editor.document.getText();
            // Accept the current suggestion.
            yield vscode.commands.executeCommand('acceptSelectedSuggestion');
            // Wait for the suggestion text to be inserted (document content should change).
            yield waitForDocumentChange(editor.document, doc => doc.getText() !== beforeAcceptContent, 3000);
            // Move cursor to the end for the next iteration.
            yield moveCursorToEOF(editor);
        }
        const finalDocumentText = editor.document.getText();
        logVerbose(`Final document text: "${finalDocumentText}"`);
        const snippetResult = {
            allText: finalDocumentText
        };
        const responseObj = {
            snippetResults: snippetResult
        };
        console.log("Final response object:", responseObj);
        yield sendTestResult(responseObj);
        yield closeVSCodeWithoutSaving();
    }));
    context.subscriptions.push(disposable);
    vscode.commands.executeCommand('snippetTester.testAllSnippets');
}
exports.activate = activate;
function deactivate() {
    console.log('Snippet Tester extension deactivated.');
}
exports.deactivate = deactivate;
