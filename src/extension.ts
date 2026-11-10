import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { PsqlMigrCliRunner } from './cliRunner';
import { SchemaObjectsTreeProvider } from './views/schemaExplorer';
import { MigrationHistoryTreeProvider } from './views/migrationExplorer';
import { ConnectionTreeProvider } from './views/connectionManager';

class SchemaDiffContentProvider implements vscode.TextDocumentContentProvider {
    private contents = new Map<string, string>();
    private _onDidChange = new vscode.EventEmitter<vscode.Uri>();
    readonly onDidChange = this._onDidChange.event;

    public setContent(uri: vscode.Uri, content: string): void {
        this.contents.set(uri.toString(), content);
        this._onDidChange.fire(uri);
    }

    provideTextDocumentContent(uri: vscode.Uri): string {
        return this.contents.get(uri.toString()) || '';
    }
}

export function activate(context: vscode.ExtensionContext) {
    const workspaceRoot = vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length > 0
        ? vscode.workspace.workspaceFolders[0].uri.fsPath
        : process.cwd();

    const cliRunner = new PsqlMigrCliRunner(workspaceRoot, context.extensionPath);

    // Virtual document provider for side-by-side schema diffs
    const diffProvider = new SchemaDiffContentProvider();
    const diffProviderReg = vscode.workspace.registerTextDocumentContentProvider('psqlmigr-diff', diffProvider);

    // Tree View Providers
    const schemaTreeProvider = new SchemaObjectsTreeProvider(workspaceRoot, cliRunner);
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
        const existingEnv: Record<string, string> = {};
        const envFilePath = path.join(workspaceRoot, '.env');
        if (fs.existsSync(envFilePath)) {
            const lines = fs.readFileSync(envFilePath, 'utf-8').split(/\r?\n/);
            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed || trimmed.startsWith('#')) {
                    continue;
                }
                const eqIdx = trimmed.indexOf('=');
                if (eqIdx > 0) {
                    const key = trimmed.substring(0, eqIdx).trim();
                    const val = trimmed.substring(eqIdx + 1).trim().replace(/^['"]|['"]$/g, '');
                    existingEnv[key] = val;
                }
            }
        }

        const host = await vscode.window.showInputBox({
            title: 'PostgreSQL Connection Setup (1/5): Host',
            prompt: 'PostgreSQL Host',
            value: existingEnv['POSTGRES_HOST'] || 'localhost',
            ignoreFocusOut: true
        });
        if (!host) {
            return;
        }

        const port = await vscode.window.showInputBox({
            title: 'PostgreSQL Connection Setup (2/5): Port',
            prompt: 'PostgreSQL Port',
            value: existingEnv['POSTGRES_PORT'] || '5432',
            ignoreFocusOut: true
        });
        if (!port) {
            return;
        }

        const user = await vscode.window.showInputBox({
            title: 'PostgreSQL Connection Setup (3/5): User',
            prompt: 'PostgreSQL User',
            value: existingEnv['POSTGRES_USER'] || 'postgres',
            ignoreFocusOut: true
        });
        if (!user) {
            return;
        }

        const password = await vscode.window.showInputBox({
            title: 'PostgreSQL Connection Setup (4/5): Password',
            prompt: 'PostgreSQL Password',
            password: true,
            ignoreFocusOut: true
        });
        if (password === undefined) {
            return;
        }

        const database = await vscode.window.showInputBox({
            title: 'PostgreSQL Connection Setup (5/5): Database Name',
            prompt: 'PostgreSQL Database Name',
            value: existingEnv['POSTGRES_DB'] || '',
            ignoreFocusOut: true
        });
        if (!database) {
            return;
        }

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
        const schemaDirPath = path.join(workspaceRoot, 'schemas');

        // Check if schemas directory exists and has existing contents
        if (fs.existsSync(schemaDirPath)) {
            const files = fs.readdirSync(schemaDirPath);
            if (files.length > 0) {
                const confirm = await vscode.window.showWarningMessage(
                    'The "schemas/" directory already contains files. Pulling from the database will OVERWRITE and CLEAR all existing DDL scripts in "schemas/". Do you want to continue?',
                    { modal: true },
                    'Overwrite & Pull'
                );
                if (confirm !== 'Overwrite & Pull') {
                    return;
                }
            }
        }

        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Reverse-engineering PostgreSQL schema into schemas/ folder...'
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

    // 4b. Compare & Sync Schema from Database (Selective Update)
    const syncSchemaCmd = vscode.commands.registerCommand('psqlmigr.syncSchema', async () => {
        const diffRes = await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Comparing PostgreSQL database schemas with local schemas/ folder...'
        }, async () => {
            return await cliRunner.diffSchema();
        });

        if (!diffRes.success) {
            vscode.window.showErrorMessage(`Schema comparison failed: ${diffRes.error || diffRes.message}`);
            return;
        }

        const diffs: Array<{
            rel_path: string;
            status: 'ADDED_IN_DB' | 'MODIFIED' | 'DELETED_IN_DB';
            db_ddl: string | null;
            local_ddl: string | null;
            diff: string;
        }> = diffRes.diffs || [];

        if (diffs.length === 0) {
            vscode.window.showInformationMessage('✓ Local schemas/ folder is completely in sync with the PostgreSQL database!');
            return;
        }

        interface DiffQuickPickItem extends vscode.QuickPickItem {
            diffItem: typeof diffs[0];
        }

        const viewDiffButton: vscode.QuickInputButton = {
            iconPath: new vscode.ThemeIcon('diff'),
            tooltip: 'Open Side-by-Side Diff (Local vs Database)'
        };

        const quickPick = vscode.window.createQuickPick<DiffQuickPickItem>();
        quickPick.title = `Schema Differences (${diffs.length} found) — Select objects to update in project`;
        quickPick.placeholder = 'Check items to apply to local schemas/ folder (click the diff icon on the right to preview SQL changes)';
        quickPick.canSelectMany = true;
        quickPick.ignoreFocusOut = true;

        const items: DiffQuickPickItem[] = diffs.map(d => {
            let icon = '$(diff-modified)';
            let statusDesc = '[MODIFIED — Update local file from DB]';
            if (d.status === 'ADDED_IN_DB') {
                icon = '$(diff-added)';
                statusDesc = '[NEW IN DB — Create file in schemas/]';
            } else if (d.status === 'DELETED_IN_DB') {
                icon = '$(diff-removed)';
                statusDesc = '[MISSING IN DB — Delete file from schemas/]';
            }

            const previewLines = (d.diff || '')
                .split(/\r?\n/)
                .filter(l => (l.startsWith('+') && !l.startsWith('+++')) || (l.startsWith('-') && !l.startsWith('---')))
                .slice(0, 3)
                .join('  ');

            return {
                label: `${icon} ${d.rel_path}`,
                description: statusDesc,
                detail: previewLines || undefined,
                picked: d.status !== 'DELETED_IN_DB',
                buttons: [viewDiffButton],
                diffItem: d
            };
        });

        quickPick.items = items;
        quickPick.selectedItems = items.filter(i => i.picked);

        quickPick.onDidTriggerItemButton(async (event) => {
            const d = event.item.diffItem;
            const localUri = vscode.Uri.parse(`psqlmigr-diff:/local/${d.rel_path}`);
            const dbUri = vscode.Uri.parse(`psqlmigr-diff:/database/${d.rel_path}`);

            diffProvider.setContent(localUri, d.local_ddl ?? '-- [File does not exist locally in schemas/]\n');
            diffProvider.setContent(dbUri, d.db_ddl ?? '-- [Object does not exist in PostgreSQL database]\n');

            await vscode.commands.executeCommand(
                'vscode.diff',
                localUri,
                dbUri,
                `Schema Diff: ${d.rel_path} (Local Project ↔ Database)`
            );
        });

        quickPick.onDidAccept(async () => {
            const selected = quickPick.selectedItems.map(i => i.diffItem.rel_path);
            quickPick.hide();

            if (selected.length === 0) {
                vscode.window.showInformationMessage('No schema differences selected. Project was not modified.');
                return;
            }

            await vscode.window.withProgress({
                location: vscode.ProgressLocation.Notification,
                title: `Updating ${selected.length} schema object(s) in schemas/...`
            }, async () => {
                const syncRes = await cliRunner.syncSchema(selected);
                if (syncRes.success) {
                    const writtenCount = syncRes.written?.length || 0;
                    const deletedCount = syncRes.deleted?.length || 0;
                    vscode.window.showInformationMessage(
                        `✓ Schema synchronized! Updated: ${writtenCount}, Deleted: ${deletedCount}.`
                    );
                    refreshAllViews();
                } else {
                    vscode.window.showErrorMessage(`Sync schema failed: ${syncRes.error || syncRes.message}`);
                }
            });
        });

        quickPick.onDidHide(() => quickPick.dispose());
        quickPick.show();
    });

    // 5. Generate Migration (Plan)
    const planCmd = vscode.commands.registerCommand('psqlmigr.generateMigration', async () => {
        const name = await vscode.window.showInputBox({
            title: 'Generate Migration (1/2): Description',
            prompt: 'Enter migration description (e.g. create_users_table)',
            placeHolder: 'create_users_table',
            ignoreFocusOut: true
        });
        if (!name) {
            return;
        }

        const versionTag = await vscode.window.showInputBox({
            title: 'Generate Migration (2/2): Version',
            prompt: 'Enter migration version (Leave empty for automatic version bump)',
            placeHolder: 'e.g. 0.1.0 or 0.2.0 (press Enter for auto-bump)',
            ignoreFocusOut: true
        });
        if (versionTag === undefined) {
            return;
        }

        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Analyzing schema dependencies & generating migration...'
        }, async () => {
            const res = await cliRunner.planMigration(name, versionTag);
            if (res.success) {
                vscode.window.showInformationMessage(`✓ Migration [${res.project_version || ''}] created: ${res.up_file}`);
                if (res.up_file) {
                    const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(`${workspaceRoot}/${res.up_file}`));
                    vscode.window.showTextDocument(doc);
                }
                refreshAllViews();
            } else {
                vscode.window.showErrorMessage(`Generate migration failed: ${res.error || res.message}`);
            }
        });
    });

    // 6. Validate Migrations (Debug Dry-Run)
    const validateCmd = vscode.commands.registerCommand('psqlmigr.validateMigrations', async () => {
        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Validating pending migrations in test transaction (dry-run)...'
        }, async () => {
            const res = await cliRunner.validateMigrations();
            if (res.success) {
                vscode.window.showInformationMessage(`✓ Dry-Run Validation Passed! All migrations executed cleanly in test transaction.`);
            } else {
                vscode.window.showErrorMessage(`Dry-Run Validation Failed: ${res.error || res.message}`);
            }
        });
    });

    // 7. Apply Migrations
    const applyCmd = vscode.commands.registerCommand('psqlmigr.applyMigrations', async () => {
        const confirm = await vscode.window.showWarningMessage(
            'Are you sure you want to apply pending migrations to the PostgreSQL database?',
            { modal: true },
            'Apply Migrations'
        );
        if (confirm !== 'Apply Migrations') {
            return;
        }

        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Applying pending migrations to PostgreSQL database...'
        }, async () => {
            const res = await cliRunner.applyMigrations();
            if (res.success) {
                vscode.window.showInformationMessage(`✓ Applied ${res.executed_migrations?.length || 0} migrations successfully!`);
                refreshAllViews();
            } else {
                vscode.window.showErrorMessage(`Apply migrations failed: ${res.error || res.message}`);
            }
        });
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

    // 9. Delete Migration
    const deleteMigrationCmd = vscode.commands.registerCommand('psqlmigr.deleteMigration', async (item?: any) => {
        let versionToDelete = item?.version;

        if (!versionToDelete) {
            const manifestRes = await cliRunner.checksum();
            if (!manifestRes.success || !Array.isArray(manifestRes.migrations) || manifestRes.migrations.length === 0) {
                vscode.window.showInformationMessage('No migration files found to delete.');
                return;
            }
            const picked = await vscode.window.showQuickPick(
                manifestRes.migrations.map((m: any) => ({
                    label: `${m.version} - ${m.name}`,
                    version: m.version
                })),
                { prompt: 'Select a migration to delete', ignoreFocusOut: true }
            );
            if (!picked) {
                return;
            }
            versionToDelete = picked.version;
        }

        const confirm = await vscode.window.showWarningMessage(
            `Are you sure you want to PERMANENTLY DELETE migration '${versionToDelete}'? This will remove both UP and DOWN files from disk.`,
            { modal: true },
            'Delete Migration'
        );
        if (confirm !== 'Delete Migration') {
            return;
        }

        const res = await cliRunner.removeMigration(versionToDelete);
        if (res.success) {
            vscode.window.showInformationMessage(`✓ Migration ${versionToDelete} deleted successfully!`);
            refreshAllViews();
        } else {
            vscode.window.showErrorMessage(`Delete migration failed: ${res.error || res.message}`);
        }
    });

    // 10. Refresh Views
    const refreshCmd = vscode.commands.registerCommand('psqlmigr.refreshViews', () => {
        refreshAllViews();
    });

    context.subscriptions.push(
        diffProviderReg,
        initCmd,
        configConnCmd,
        testConnCmd,
        pullSchemaCmd,
        syncSchemaCmd,
        planCmd,
        validateCmd,
        applyCmd,
        checksumCmd,
        deleteMigrationCmd,
        refreshCmd
    );
}

export function deactivate() {}
