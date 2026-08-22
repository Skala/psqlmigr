import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { PsqlMigrCliRunner } from '../cliRunner';

export class MigrationItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly version: string,
        public readonly status: 'APPLIED' | 'PENDING' | 'LOCAL',
        public readonly upFileUri?: vscode.Uri
    ) {
        super(label, vscode.TreeItemCollapsibleState.None);

        this.description = `[${status}]`;
        this.contextValue = 'migration';

        if (upFileUri) {
            this.command = {
                command: 'vscode.open',
                title: 'Open Migration UP File',
                arguments: [upFileUri]
            };
        }

        if (status === 'APPLIED') {
            this.iconPath = new vscode.ThemeIcon('pass-filled', new vscode.ThemeColor('testing.iconPassed'));
        } else if (status === 'PENDING') {
            this.iconPath = new vscode.ThemeIcon('history', new vscode.ThemeColor('testing.iconQueued'));
        } else {
            this.iconPath = new vscode.ThemeIcon('file-code');
        }
    }
}

export class MigrationHistoryTreeProvider implements vscode.TreeDataProvider<MigrationItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<MigrationItem | undefined | null | void> = new vscode.EventEmitter<MigrationItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<MigrationItem | undefined | null | void> = this._onDidChangeTreeData.event;

    constructor(
        private workspaceRoot: string,
        private cliRunner: PsqlMigrCliRunner
    ) {}

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: MigrationItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: MigrationItem): Promise<MigrationItem[]> {
        if (element) {
            return [];
        }

        const migrationsDir = path.join(this.workspaceRoot, 'migrations');
        if (!fs.existsSync(migrationsDir)) {
            return [];
        }

        // Try getting CLI status
        const cliResult = await this.cliRunner.getStatus();
        const appliedMap = new Map<string, string>();

        if (cliResult.success && Array.isArray(cliResult.migrations)) {
            for (const item of cliResult.migrations) {
                if (item.status === 'APPLIED') {
                    appliedMap.set(item.version, item.applied_at || 'APPLIED');
                }
            }
        }

        // Read local migration files (check migrations/up/ first, then fallback to migrations/)
        const upDir = path.join(migrationsDir, 'up');
        const items: MigrationItem[] = [];

        if (fs.existsSync(upDir)) {
            const files = fs.readdirSync(upDir).filter(f => f.endsWith('.sql'));
            for (const file of files) {
                const version_name = file.slice(0, -4);
                const [version, ...nameParts] = version_name.split('_');
                const name = nameParts.join('_') || version_name;
                const isApplied = appliedMap.has(version);
                const upUri = vscode.Uri.file(path.join(upDir, file));

                items.push(new MigrationItem(
                    `${version} - ${name}`,
                    version,
                    isApplied ? 'APPLIED' : 'PENDING',
                    upUri
                ));
            }
        }

        // Legacy root .up.sql files
        const legacyFiles = fs.readdirSync(migrationsDir).filter(f => f.endsWith('.up.sql'));
        for (const file of legacyFiles) {
            const version_name = file.slice(0, -7);
            const [version, ...nameParts] = version_name.split('_');
            const name = nameParts.join('_') || version_name;
            if (!items.some(i => i.version === version)) {
                const isApplied = appliedMap.has(version);
                const upUri = vscode.Uri.file(path.join(migrationsDir, file));

                items.push(new MigrationItem(
                    `${version} - ${name}`,
                    version,
                    isApplied ? 'APPLIED' : 'PENDING',
                    upUri
                ));
            }
        }

        return items;
    }
}
