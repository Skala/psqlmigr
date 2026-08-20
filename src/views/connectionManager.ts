import * as vscode from 'vscode';
import { PsqlMigrCliRunner } from '../cliRunner';

export class ConnectionItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly description: string,
        public readonly icon: string
    ) {
        super(label, vscode.TreeItemCollapsibleState.None);
        this.description = description;
        this.iconPath = new vscode.ThemeIcon(icon);
    }
}

export class ConnectionTreeProvider implements vscode.TreeDataProvider<ConnectionItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<ConnectionItem | undefined | null | void> = new vscode.EventEmitter<ConnectionItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<ConnectionItem | undefined | null | void> = this._onDidChangeTreeData.event;

    private cliRunner: PsqlMigrCliRunner;

    constructor(private workspaceRoot: string) {
        this.cliRunner = new PsqlMigrCliRunner(workspaceRoot);
    }

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: ConnectionItem): vscode.TreeItem {
        return element;
    }

    async getChildren(element?: ConnectionItem): Promise<ConnectionItem[]> {
        if (element) {
            return [];
        }

        const connTest = await this.cliRunner.testConnection();

        if (connTest.success) {
            const details = connTest.details || {};
            return [
                new ConnectionItem('Status', 'Connected (Online)', 'check-all'),
                new ConnectionItem('Database', details.database || 'PostgreSQL', 'database'),
                new ConnectionItem('User', details.user || 'postgres', 'account'),
                new ConnectionItem('Server', details.version ? details.version.split(' ')[0] : 'PostgreSQL', 'server')
            ];
        } else {
            return [
                new ConnectionItem('Status', 'Disconnected (Offline)', 'error'),
                new ConnectionItem('Action', 'Click "Configure Connection" to setup .env', 'gear')
            ];
        }
    }
}
