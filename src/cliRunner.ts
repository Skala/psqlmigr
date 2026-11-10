import * as vscode from 'vscode';
import { exec } from 'child_process';
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
    private envSetupPromise: Promise<boolean> | null = null;

    constructor(workspaceRoot?: string, extensionPath?: string) {
        this.workspaceRoot = workspaceRoot || (vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length > 0 ? vscode.workspace.workspaceFolders[0].uri.fsPath : process.cwd());
        this.extensionPath = extensionPath || this.workspaceRoot;
    }

    private findExistingVenvCli(): string | null {
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
        return null;
    }

    private execAsync(cmd: string, cwd: string): Promise<{ stdout: string; stderr: string }> {
        return new Promise((resolve, reject) => {
            exec(cmd, { cwd }, (error, stdout, stderr) => {
                if (error) {
                    reject(new Error(stderr || error.message || stdout));
                } else {
                    resolve({ stdout, stderr });
                }
            });
        });
    }

    private async detectSystemPython(cwd: string): Promise<string> {
        const candidates = process.platform === 'win32'
            ? ['python', 'py -3', 'python3']
            : ['python3', 'python'];

        for (const cmd of candidates) {
            try {
                await this.execAsync(`${cmd} --version`, cwd);
                return cmd;
            } catch {
                // Try next candidate
            }
        }
        return 'python';
    }

    public async ensurePythonEnv(forceReinstall: boolean = false): Promise<boolean> {
        if (!forceReinstall && this.findExistingVenvCli()) {
            return true;
        }

        if (this.envSetupPromise) {
            return this.envSetupPromise;
        }

        this.envSetupPromise = (async () => {
            const coreEngineDir = path.join(this.extensionPath, 'core_engine');
            const pyprojectPath = path.join(coreEngineDir, 'pyproject.toml');

            if (!fs.existsSync(pyprojectPath)) {
                return false;
            }

            return await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: 'PsqlMigr: First-time setup — installing Python engine & dependencies (.venv)...'
            }, async (progress) => {
                try {
                    const venvDir = path.join(coreEngineDir, '.venv');
                    const sysPython = await this.detectSystemPython(coreEngineDir);

                    const venvPython = process.platform === 'win32'
                        ? path.join(venvDir, 'Scripts', 'python.exe')
                        : path.join(venvDir, 'bin', 'python');

                    if (!fs.existsSync(venvPython)) {
                        progress.report({ message: 'Creating virtual environment (.venv)...' });
                        await this.execAsync(`${sysPython} -m venv "${venvDir}"`, coreEngineDir);
                    }

                    progress.report({ message: 'Installing psqlmigr-core packages (typer, psycopg, sqlglot, rich)...' });
                    await this.execAsync(`"${venvPython}" -m pip install -e "${coreEngineDir}"`, coreEngineDir);

                    return this.findExistingVenvCli() !== null;
                } catch (err: any) {
                    vscode.window.showErrorMessage(
                        `PsqlMigr Python environment setup failed: ${err?.message || err}`
                    );
                    return false;
                }
            });
        })();

        try {
            return await this.envSetupPromise;
        } finally {
            this.envSetupPromise = null;
        }
    }

    private getCliCommand(): string {
        const venvCli = this.findExistingVenvCli();
        if (venvCli) {
            return venvCli;
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

    public async execute<T = any>(args: string[], isRetry: boolean = false): Promise<CliResult<T>> {
        await this.ensurePythonEnv(false);

        const cliCmd = this.getCliCommand();
        const commandStr = `${cliCmd} ${args.join(' ')} --json`;

        return new Promise((resolve) => {
            exec(commandStr, { cwd: this.workspaceRoot }, async (error, stdout, stderr) => {
                if (stdout) {
                    try {
                        const parsed = JSON.parse(stdout.trim());
                        resolve(parsed);
                        return;
                    } catch (e) {
                        // Not JSON output
                    }
                }

                const combinedErr = `${stderr || ''}\n${error?.message || ''}\n${stdout || ''}`;
                if (!isRetry && combinedErr.includes('ModuleNotFoundError')) {
                    const repaired = await this.ensurePythonEnv(true);
                    if (repaired) {
                        const retryRes = await this.execute<T>(args, true);
                        resolve(retryRes);
                        return;
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
            if (params.host) { args.push('--host', `"${params.host}"`); }
            if (params.port) { args.push('--port', `"${params.port}"`); }
            if (params.user) { args.push('--user', `"${params.user}"`); }
            if (params.password) { args.push('--password', `"${params.password}"`); }
            if (params.database) { args.push('--database', `"${params.database}"`); }
        }
        return this.execute(args);
    }

    public async pullSchema(): Promise<CliResult> {
        return this.execute(['pull']);
    }

    public async diffSchema(): Promise<CliResult> {
        return this.execute(['diff']);
    }

    public async syncSchema(selectedFiles: string[]): Promise<CliResult> {
        const args = ['sync'];
        for (const f of selectedFiles) {
            args.push('--file', `"${f}"`);
        }
        return this.execute(args);
    }

    public async planMigration(name: string, version?: string): Promise<CliResult> {
        const args = ['plan', `"${name}"`];
        if (version && version.trim()) {
            args.push('--version', `"${version.trim()}"`);
        }
        return this.execute(args);
    }

    public async removeMigration(version: string): Promise<CliResult> {
        return this.execute(['remove-migration', `"${version}"`]);
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
