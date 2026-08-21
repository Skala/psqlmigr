import * as vscode from 'vscode';
import { PsqlMigrCliRunner } from './cliRunner';
import { SchemaObjectsTreeProvider } from './views/schemaExplorer';
import { MigrationHistoryTreeProvider } from './views/migrationExplorer';
import { ConnectionTreeProvider } from './views/connectionManager';

export function activate(context: vscode.ExtensionContext) {
    const workspaceRoot = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length > 0
        ? vscode.workspace.workspaceFolders[0].uri.fsPath
        : process.cwd();

    const cliRunner = new PsqlMigrCliRunner(workspaceRoot, context.extensionPath);

    // Tree View Providers
    const schemaTreeProvider = new SchemaObjectsTreeProvider(workspaceRoot);
    const migrationTreeProvider = new MigrationHistoryTreeProvider(workspaceRoot, cliRunner);
    const connectionTreeProvider = new ConnectionTreeProvider(workspaceRoot, cliRunner);

    vscode.window.registerTreeDataProvider('psqlmigr-schema', schemaTreeProvider);
    vscode.window.registerTreeDataProvider('psqlmigr-migrations', migrationTreeProvider);
    vscode.window.registerTreeDataProvider('psqlmigr-connection', connectionTreeProvider);

    const refreshAllViews = () => {
        schemaTreeProvider.refresh();
        migrationTreeProvider.refresh();
        connectionTreeProvider.refresh();
    };

    // Register Commands

    // 1. Init Project
    const initCmd = vscode.commands.registerCommand('psqlmigr.initProject', async () => {
        const res = await cliRunner.initProject();
        if (res.success) {
            vscode.window.showInformationMessage('psqlmigr project initialized successfully!');
            refreshAllViews();
        } else {
            vscode.window.showErrorMessage(`Initialization failed: ${res.error || res.message}`);
        }
    });

    // 2. Configure Connection & Save to .env
    const configConnCmd = vscode.commands.registerCommand('psqlmigr.configureConnection', async () => {
        const host = await vscode.window.showInputBox({ prompt: 'PostgreSQL Host', value: 'localhost' });
        if (!host) return;

        const port = await vscode.window.showInputBox({ prompt: 'PostgreSQL Port', value: '5432' });
        if (!port) return;

        const user = await vscode.window.showInputBox({ prompt: 'PostgreSQL User', value: 'postgres' });
        if (!user) return;

        const password = await vscode.window.showInputBox({ prompt: 'PostgreSQL Password', password: true });
        if (password === undefined) return;

        const database = await vscode.window.showInputBox({ prompt: 'PostgreSQL Database Name' });
        if (!database) return;

        const saveRes = await cliRunner.setEnv({ host, port, user, password, database });
        if (!saveRes.success) {
            vscode.window.showErrorMessage(`Failed to save .env: ${saveRes.error}`);
            return;
        }

        // Test connection immediately
        const testRes = await cliRunner.testConnection();
        if (testRes.success) {
            vscode.window.showInformationMessage('✓ Connection successful and saved to .env!');
        } else {
            vscode.window.showWarningMessage(`Saved to .env, but connection test failed: ${testRes.error || testRes.message}`);
        }
        refreshAllViews();
    });

    // 3. Test Connection
    const testConnCmd = vscode.commands.registerCommand('psqlmigr.testConnection', async () => {
        const res = await cliRunner.testConnection();
        if (res.success) {
            vscode.window.showInformationMessage(`✓ PostgreSQL Connection Successful! (${res.details?.database || ''})`);
        } else {
            vscode.window.showErrorMessage(`✗ Connection Failed: ${res.error || res.message}`);
        }
        refreshAllViews();
    });

    // 4. Pull Schema from DB
    const pullSchemaCmd = vscode.commands.registerCommand('psqlmigr.pullSchema', async () => {
        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Reverse-engineering PostgreSQL schema into schema/ folder...'
        }, async () => {
            const res = await cliRunner.pullSchema();
            if (res.success) {
                vscode.window.showInformationMessage(`✓ Successfully pulled schema! (${res.files_written?.length || 0} DDL files generated)`);
                refreshAllViews();
            } else {
                vscode.window.showErrorMessage(`Pull schema failed: ${res.error || res.message}`);
            }
        });
    });

    // 5. Generate Migration (Plan)
    const planCmd = vscode.commands.registerCommand('psqlmigr.generateMigration', async () => {
        const name = await vscode.window.showInputBox({
            prompt: 'Enter migration description (e.g. create_users_table)',
            placeHolder: 'create_users_table'
        });
        if (!name) return;

        const res = await cliRunner.planMigration(name);
        if (res.success) {
            vscode.window.showInformationMessage(`✓ Migration files created: ${res.up_file}`);
            if (res.up_file) {
                const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(`${workspaceRoot}/${res.up_file}`));
                vscode.window.showTextDocument(doc);
            }
            refreshAllViews();
        } else {
            vscode.window.showErrorMessage(`Generate migration failed: ${res.error || res.message}`);
        }
    });

    // 6. Validate Migrations (Debug Dry-Run)
    const validateCmd = vscode.commands.registerCommand('psqlmigr.validateMigrations', async () => {
        const res = await cliRunner.validateMigrations();
        if (res.success) {
            vscode.window.showInformationMessage(`✓ Dry-Run Validation Passed! All migrations executed cleanly in test transaction.`);
        } else {
            vscode.window.showErrorMessage(`Dry-Run Validation Failed: ${res.error || res.message}`);
        }
    });

    // 7. Apply Migrations
    const applyCmd = vscode.commands.registerCommand('psqlmigr.applyMigrations', async () => {
        const confirm = await vscode.window.showWarningMessage(
            'Are you sure you want to apply pending migrations to the PostgreSQL database?',
            { modal: true },
            'Apply Migrations'
        );
        if (confirm !== 'Apply Migrations') return;

        const res = await cliRunner.applyMigrations();
        if (res.success) {
            vscode.window.showInformationMessage(`✓ Applied ${res.executed_migrations?.length || 0} migrations successfully!`);
            refreshAllViews();
        } else {
            vscode.window.showErrorMessage(`Apply migrations failed: ${res.error || res.message}`);
        }
    });

    // 8. Recalculate Checksums
    const checksumCmd = vscode.commands.registerCommand('psqlmigr.recalculateChecksums', async () => {
        const res = await cliRunner.checksum();
        if (res.success) {
            vscode.window.showInformationMessage('✓ Recalculated migration SHA256 checksums successfully!');
        } else {
            vscode.window.showErrorMessage(`Recalculate checksums failed: ${res.error || res.message}`);
        }
    });

    // 9. Refresh Views
    const refreshCmd = vscode.commands.registerCommand('psqlmigr.refreshViews', () => {
        refreshAllViews();
    });

    context.subscriptions.push(
        initCmd,
        configConnCmd,
        testConnCmd,
        pullSchemaCmd,
        planCmd,
        validateCmd,
        applyCmd,
        checksumCmd,
        refreshCmd
    );
}

export function deactivate() {}
