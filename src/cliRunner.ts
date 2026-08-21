import * as vscode from 'vscode';
import { exec, execSync } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

export interface CliResult<T = any> {
    success: boolean;
    message?: string;
    error?: string;
    [key: string]: any;
}

export class PsqlMigrCliRunner {
    private workspaceRoot: string;
    private extensionPath: string;

    constructor(workspaceRoot?: string, extensionPath?: string) {
        this.workspaceRoot = workspaceRoot || (vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length > 0 ? vscode.workspace.workspaceFolders[0].uri.fsPath : process.cwd());
        this.extensionPath = extensionPath || this.workspaceRoot;
    }

    private getCliCommand(): string {
        const pathsToTest = [
            path.join(this.extensionPath, 'core_engine', '.venv', 'Scripts', 'psqlmigr.exe'),
            path.join(this.workspaceRoot, 'core_engine', '.venv', 'Scripts', 'psqlmigr.exe'),
            path.join(this.extensionPath, 'core_engine', '.venv', 'bin', 'psqlmigr'),
            path.join(this.workspaceRoot, 'core_engine', '.venv', 'bin', 'psqlmigr'),
        ];

        for (const p of pathsToTest) {
            if (fs.existsSync(p)) {
                return `"${p}"`;
            }
        }

        const winPy = path.join(this.extensionPath, 'core_engine', '.venv', 'Scripts', 'python.exe');
        const unixPy = path.join(this.extensionPath, 'core_engine', '.venv', 'bin', 'python');
        const cliPy = path.join(this.extensionPath, 'core_engine', 'psqlmigr', 'cli.py');

        if (fs.existsSync(winPy) && fs.existsSync(cliPy)) {
            return `"${winPy}" "${cliPy}"`;
        }
        if (fs.existsSync(unixPy) && fs.existsSync(cliPy)) {
            return `"${unixPy}" "${cliPy}"`;
        }

        if (fs.existsSync(cliPy)) {
            return `python "${cliPy}"`;
        }

        return 'python -m psqlmigr.cli';
    }

    public async execute<T = any>(args: string[]): Promise<CliResult<T>> {
        const cliCmd = this.getCliCommand();
        const commandStr = `${cliCmd} ${args.join(' ')} --json`;

        return new Promise((resolve) => {
            exec(commandStr, { cwd: this.workspaceRoot }, (error, stdout, stderr) => {
                if (stdout) {
                    try {
                        const parsed = JSON.parse(stdout.trim());
                        resolve(parsed);
                        return;
                    } catch (e) {
                        // Not JSON output
                    }
                }

                if (error) {
                    resolve({
                        success: false,
                        error: stderr || error.message || stdout
                    });
                } else {
                    resolve({
                        success: true,
                        message: stdout
                    });
                }
            });
        });
    }

    public async initProject(): Promise<CliResult> {
        return this.execute(['init']);
    }

    public async testConnection(): Promise<CliResult> {
        return this.execute(['test-connection']);
    }

    public async setEnv(params: { host?: string; port?: string; user?: string; password?: string; database?: string; url?: string }): Promise<CliResult> {
        const args = ['set-env'];
        if (params.url) {
            args.push('--url', `"${params.url}"`);
        } else {
            if (params.host) args.push('--host', `"${params.host}"`);
            if (params.port) args.push('--port', `"${params.port}"`);
            if (params.user) args.push('--user', `"${params.user}"`);
            if (params.password) args.push('--password', `"${params.password}"`);
            if (params.database) args.push('--database', `"${params.database}"`);
        }
        return this.execute(args);
    }

    public async pullSchema(): Promise<CliResult> {
        return this.execute(['pull']);
    }

    public async planMigration(name: string): Promise<CliResult> {
        return this.execute(['plan', `"${name}"`]);
    }

    public async validateMigrations(): Promise<CliResult> {
        return this.execute(['validate']);
    }

    public async applyMigrations(): Promise<CliResult> {
        return this.execute(['apply']);
    }

    public async getStatus(): Promise<CliResult> {
        return this.execute(['status']);
    }

    public async checksum(): Promise<CliResult> {
        return this.execute(['checksum']);
    }
}
