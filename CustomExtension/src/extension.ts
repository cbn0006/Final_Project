import * as vscode from 'vscode';
import * as fs from 'fs';
import * as path from 'path';
import { parse } from 'csv-parse/sync';
import fetch from 'node-fetch';

const verbose = true;

async function sendTestResult(result: any) {
    try {
        // Dynamically import node-fetch for ESM support
        const response = await fetch("http://127.0.0.1:5000/report", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(result)
        });
        const data = await response.json();
        console.log("Server response:", data);
        return data;
    } catch (error) {
        vscode.window.showErrorMessage("Failed to report test result: " + error);
        return null;
    }
}

export function activate(context: vscode.ExtensionContext) {
    console.log('Snippet Tester extension activated.');

    let disposable = vscode.commands.registerCommand('snippetTester.testAllSnippets', async () => {
        const logMessages: string[] = [];
        const snippetResults: any[] = [];
        const logVerbose = (msg: string) => {
            console.log(msg);
            if (verbose) logMessages.push(msg);
        };

        let snippetsCsvPath: string;
        if (vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length > 0) {
            snippetsCsvPath = path.join(vscode.workspace.workspaceFolders[0].uri.fsPath, 'snippets.csv');
        } else {
            snippetsCsvPath = path.join(process.cwd(), 'snippets.csv');
        }

        if (!fs.existsSync(snippetsCsvPath)) {
            vscode.window.showErrorMessage(`Snippets CSV file not found at ${snippetsCsvPath}`);
            return;
        }

        let csvContent: string;
        try {
            csvContent = fs.readFileSync(snippetsCsvPath, 'utf8');
        } catch (err) {
            vscode.window.showErrorMessage(`Failed to read snippets CSV file: ${err}`);
            return;
        }

        // Use csv-parse to parse the CSV into records.
        let snippetRecords: any[] = [];
        try {
            snippetRecords = parse(csvContent, {
                columns: true,
                skip_empty_lines: true
            });
        } catch (error) {
            vscode.window.showErrorMessage(`Error parsing CSV file: ${error}`);
            return;
        }

        const document = await vscode.workspace.openTextDocument({ content: '', language: 'python' });
        const editor = await vscode.window.showTextDocument(document);

        for (let i = 0; i < snippetRecords.length; i++) {
            const record = snippetRecords[i];
            const key = record["key"];
            const prefix = record["prefix"];
            logVerbose(`Testing snippet '${key}' with prefix "${prefix}"`);
        
            const lastLine = editor.document.lineAt(editor.document.lineCount - 1);
            const eofPosition = lastLine.range.end;
            editor.selection = new vscode.Selection(eofPosition, eofPosition);
        
            if (i !== 0) {
                await vscode.commands.executeCommand('type', { text: '\n' });
                await delay(200);
            }
        
            await vscode.commands.executeCommand('type', { text: prefix });
            await delay(1500);
            await vscode.commands.executeCommand('editor.action.triggerSuggest');
            await delay(2000);
            await vscode.commands.executeCommand('acceptSelectedSuggestion');
            await delay(2000);
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

        await sendTestResult(responseObj);
        await closeVSCodeWithoutSaving();
    });

    context.subscriptions.push(disposable);
    vscode.commands.executeCommand('snippetTester.testAllSnippets');
}

export function deactivate() {
    console.log('Snippet Tester extension deactivated.');
}

function delay(ms: number) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function closeVSCodeWithoutSaving() {
    while (vscode.window.visibleTextEditors.length > 0) {
        await vscode.commands.executeCommand('workbench.action.revertAndCloseActiveEditor');
        await delay(500);
    }
    await vscode.commands.executeCommand('workbench.action.closeWindow');
}