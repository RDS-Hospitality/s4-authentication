import { Rule, Tree, SchematicContext } from '@angular-devkit/schematics';
import * as ts from 'typescript';

const FEATURE = 'withInterceptors([graphqlAuthInterceptor])';
const HTTP_MODULE = '@angular/common/http';
const INTERCEPTOR_IMPORT = "import { graphqlAuthInterceptor } from './auth/graphql-auth';\n";

/**
 * Wire the C9 bearer interceptor into a standalone app's `provideHttpClient(...)`.
 *
 * WHY THIS EXISTS: provide-auth.ts registers the class interceptor through the
 * HTTP_INTERCEPTORS multi-provider, which reaches `HttpClientModule` and
 * `provideHttpClient(withInterceptorsFromDi())` apps. A bare `provideHttpClient()` —
 * Angular 17's standalone default — ignores class interceptors, silently, and the
 * build cannot tell. So the installer inserts the functional feature into that call.
 *
 * Same discipline as add-routes.ts: parse with the TypeScript compiler API and edit the
 * `provideHttpClient` CALL EXPRESSION, never a text search — a mention in a comment, a
 * second call outside the providers array, or a call split across lines must not be
 * touched or mistaken for wiring. Graceful by design: a missing host file or no
 * provider produces a warning and an unchanged tree. Idempotent: an existing
 * `withInterceptors(`/`withInterceptorsFromDi(` argument, or an `HttpClientModule`
 * import, means nothing is inserted.
 */
export function addHttpClientInterceptor(hostPath: string | undefined): Rule {
  return (tree: Tree, context: SchematicContext) => {
    if (!hostPath || !tree.exists(hostPath)) {
      context.logger.warn(
        `s4-auth-angular: no app.config.ts or app.module.ts found. If your app uses ` +
          `HttpClient via provideHttpClient(), add withInterceptors([graphqlAuthInterceptor]) ` +
          `to it (import from './auth/graphql-auth') so GraphQL requests carry the user's token.`,
      );
      return tree;
    }

    const text = tree.read(hostPath)!.toString('utf-8');
    const source = ts.createSourceFile(hostPath, text, ts.ScriptTarget.Latest, true);

    if (importsHttpClientModule(source)) {
      return tree; // HttpClientModule honours HTTP_INTERCEPTORS; provide-auth covers it
    }

    const calls = collectProvideHttpClientCalls(source);
    if (calls.length === 0) {
      context.logger.warn(
        `s4-auth-angular: ${hostPath} has no provideHttpClient(...) call in a form this installer ` +
          `recognises (a direct, un-aliased call). If your app uses HttpClient, include ` +
          `withInterceptors([graphqlAuthInterceptor]) (import from './auth/graphql-auth') in that ` +
          `call so GraphQL requests carry the user's token; HttpClientModule apps need nothing.`,
      );
      return tree;
    }

    const target = pickTarget(calls, source);
    if (calls.length > 1) {
      context.logger.info(
        `s4-auth-angular: ${calls.length} provideHttpClient() calls in ${hostPath}; wiring the one in the providers array only.`,
      );
    }
    if (hasFromDiFeature(target, source)) {
      return tree; // withInterceptorsFromDi() honours the class interceptor provide-auth registers
    }
    if (text.includes('graphqlAuthInterceptor')) {
      return tree; // already wired (idempotent)
    }

    const recorder = tree.beginUpdate(hostPath);
    const args = target.arguments;
    const existing = findWithInterceptorsArray(target, source);
    if (existing === 'opaque') {
      // withInterceptors(someVariable) — cannot see inside; a bare provideHttpClient() with
      // its own functional interceptors ignores HTTP_INTERCEPTORS, so say so rather than skip.
      context.logger.warn(
        `s4-auth-angular: ${hostPath} calls provideHttpClient(withInterceptors(<expression>)). ` +
          `Add graphqlAuthInterceptor (from './auth/graphql-auth') to that interceptor list ` +
          `yourself — without it GraphQL requests carry no token.`,
      );
      return tree;
    }
    if (existing) {
      // provideHttpClient(withInterceptors([theirs])) — join the existing list.
      const sep = existing.elements.length > 0 ? ', ' : '';
      recorder.insertLeft(existing.getEnd() - 1, `${sep}graphqlAuthInterceptor`);
    } else if (args.length === 0) {
      recorder.insertLeft(target.getEnd() - 1, FEATURE);
    } else {
      recorder.insertLeft(args[0].getStart(source), `${FEATURE}, `);
    }

    const httpImport = findNamedImport(source, HTTP_MODULE);
    if (!existing) {
      if (httpImport && !httpImport.names.includes('withInterceptors')) {
        recorder.insertLeft(httpImport.lastNameEnd, ', withInterceptors');
      } else if (!httpImport) {
        recorder.insertLeft(0, `import { withInterceptors } from '${HTTP_MODULE}';\n`);
      }
    }
    if (!findNamedImport(source, './auth/graphql-auth')) {
      recorder.insertLeft(0, INTERCEPTOR_IMPORT);
    }
    tree.commitUpdate(recorder);
    return tree;
  };
}

function importsHttpClientModule(source: ts.SourceFile): boolean {
  const imp = findNamedImport(source, HTTP_MODULE);
  return !!imp && imp.names.includes('HttpClientModule');
}

function collectProvideHttpClientCalls(source: ts.SourceFile): ts.CallExpression[] {
  const found: ts.CallExpression[] = [];
  const visit = (node: ts.Node): void => {
    if (
      ts.isCallExpression(node) &&
      ts.isIdentifier(node.expression) &&
      node.expression.text === 'provideHttpClient'
    ) {
      found.push(node);
    }
    ts.forEachChild(node, visit);
  };
  visit(source);
  return found;
}

/** Prefer the call that sits inside a `providers: [...]` array; else the first call. */
function pickTarget(calls: ts.CallExpression[], source: ts.SourceFile): ts.CallExpression {
  for (const call of calls) {
    let node: ts.Node | undefined = call.parent;
    while (node) {
      if (
        ts.isPropertyAssignment(node) &&
        node.name.getText(source) === 'providers' &&
        ts.isArrayLiteralExpression(node.initializer)
      ) {
        return call;
      }
      node = node.parent;
    }
  }
  return calls[0];
}

function hasFromDiFeature(call: ts.CallExpression, source: ts.SourceFile): boolean {
  return call.arguments.some((arg) => arg.getText(source).startsWith('withInterceptorsFromDi('));
}

/**
 * The array literal inside an existing `withInterceptors([...])` argument, `'opaque'` when
 * the argument is something we cannot see into, or undefined when there is no such feature.
 */
function findWithInterceptorsArray(
  call: ts.CallExpression,
  source: ts.SourceFile,
): ts.ArrayLiteralExpression | 'opaque' | undefined {
  for (const arg of call.arguments) {
    if (
      ts.isCallExpression(arg) &&
      ts.isIdentifier(arg.expression) &&
      arg.expression.text === 'withInterceptors'
    ) {
      const list = arg.arguments[0];
      return list && ts.isArrayLiteralExpression(list) ? list : 'opaque';
    }
  }
  void source;
  return undefined;
}

function findNamedImport(
  source: ts.SourceFile,
  moduleSpecifier: string,
): { names: string[]; lastNameEnd: number } | undefined {
  for (const stmt of source.statements) {
    if (
      ts.isImportDeclaration(stmt) &&
      ts.isStringLiteral(stmt.moduleSpecifier) &&
      stmt.moduleSpecifier.text === moduleSpecifier &&
      stmt.importClause?.namedBindings &&
      ts.isNamedImports(stmt.importClause.namedBindings)
    ) {
      const bindings = stmt.importClause.namedBindings;
      const last = bindings.elements[bindings.elements.length - 1];
      return {
        names: bindings.elements.map((e) => e.name.text),
        lastNameEnd: last ? last.getEnd() : bindings.getEnd() - 1,
      };
    }
  }
  return undefined;
}
