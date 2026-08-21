import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { PsqlMigrCliRunner } from '../cliRunner';

export class SchemaItem extends vscode.TreeItem {
    constructor(
        public readonly label: string,
        public readonly collapsibleState: vscode.TreeItemCollapsibleState,
        public readonly itemType: 'schema' | 'category' | 'file',
        public readonly resourceUri?: vscode.Uri
    ) {
        super(label, collapsibleState);
        this.contextValue = itemType;

        if (itemType === 'file' && resourceUri) {
            this.command = {
                command: 'vscode.open',
                title: 'Open File',
                arguments: [resourceUri]
            };
            this.iconPath = new vscode.ThemeIcon('symbol-structure');
        } else if (itemType === 'category') {
            this.iconPath = new vscode.ThemeIcon('folder-opened');
        } else if (itemType === 'schema') {
            this.iconPath = new vscode.ThemeIcon('database');
        }
    }
}

export class SchemaObjectsTreeProvider implements vscode.TreeDataProvider<SchemaItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<SchemaItem | undefined | null | void> = new vscode.EventEmitter<SchemaItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<SchemaItem | undefined | null | void> = this._onDidChangeTreeData.event;

    constructor(
        private workspaceRoot: string,
        private cliRunner?: PsqlMigrCliRunner
    ) {}

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: SchemaItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: SchemaItem): Thenable<SchemaItem[]> {
        const schemaDirPath = path.join(this.workspaceRoot, 'schema');

        if (!fs.existsSync(schemaDirPath)) {
            return Promise.resolve([]);
        }

        if (!element) {
            // Root level: List schemas (subdirectories of schema/)
            const entries = fs.readdirSync(schemaDirPath, { withFileTypes: true });
            const schemaFolders = entries
                .filter(dirent => dirent.isDirectory())
                .map(dirent => new SchemaItem(dirent.name, vscode.TreeItemCollapsibleState.Collapsed, 'schema'));

            return Promise.resolve(schemaFolders);
        }

        if (element.itemType === 'schema') {
            // Under schema folder: List category subdirectories (tables, functions, procedures, views, etc.)
            const schemaFolderPath = path.join(schemaDirPath, element.label);
            if (!fs.existsSync(schemaFolderPath)) {
                return Promise.resolve([]);
            }

            const entries = fs.readdirSync(schemaFolderPath, { withFileTypes: true });
            const categories = entries
                .filter(dirent => dirent.isDirectory())
                .map(dirent => new SchemaItem(dirent.name, vscode.TreeItemCollapsibleState.Collapsed, 'category'));

            return Promise.resolve(categories);
        }

        if (element.itemType === 'category') {
            // Under category folder: List .sql files
            const schemaName = element.label;
            // Get parent schema name from parent item path
            const categoryFolderPath = this.findCategoryPath(schemaDirPath, element.label);
            if (!categoryFolderPath || !fs.existsSync(categoryFolderPath)) {
                return Promise.resolve([]);
            }

            const entries = fs.readdirSync(categoryFolderPath, { withFileTypes: true });
            const files = entries
                .filter(dirent => dirent.isFile() && dirent.name.endsWith('.sql'))
                .map(dirent => {
                    const filePath = path.join(categoryFolderPath, dirent.name);
                    return new SchemaItem(dirent.name, vscode.TreeItemCollapsibleState.None, 'file', vscode.Uri.file(filePath));
                });

            return Promise.resolve(files);
        }

        return Promise.resolve([]);
    }

    private findCategoryPath(schemaDirPath: string, categoryName: string): string | null {
        const schemas = fs.readdirSync(schemaDirPath, { withFileTypes: true }).filter(d => d.isDirectory());
        for (const s of schemas) {
            const catPath = path.join(schemaDirPath, s.name, categoryName);
            if (fs.existsSync(catPath)) {
                return catPath;
            }
        }
        return null;
    }
}
