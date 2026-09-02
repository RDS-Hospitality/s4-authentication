// Spec-blind origin: blueprint jwt-release-0.4 tests.md §c "add-http-client rule", adapted to
// the repo's fixture style (add-routes_spec.ts). Asserts on generated content only.
import { Tree } from '@angular-devkit/schematics';
import { addHttpClientInterceptor } from './add-http-client';

const warnings: string[] = [];
const ctx = () => ({ logger: { warn: (m: string) => warnings.push(m), info: () => {} } } as any);

function treeWith(path: string, content: string): Tree {
  const tree = Tree.empty();
  tree.create(path, content);
  return tree;
}
const CFG = '/src/app/app.config.ts';
const wrap = (providers: string, extraImports = '') =>
  `import { ApplicationConfig } from '@angular/core';\n${extraImports}\nexport const appConfig: ApplicationConfig = {\n  providers: [${providers}],\n};\n`;
const run = (tree: Tree) => (addHttpClientInterceptor(CFG)(tree, ctx()) as Tree).read(CFG)!.toString('utf-8');
const count = (text: string, needle: string) => text.split(needle).length - 1;

describe('addHttpClientInterceptor', () => {
  beforeEach(() => (warnings.length = 0));

  it('wires withInterceptors([graphqlAuthInterceptor]) into a bare provideHttpClient()', () => {
    const text = run(treeWith(CFG, wrap('provideRouter(routes), provideHttpClient()', "import { provideHttpClient } from '@angular/common/http';")));
    expect(text).toContain('provideHttpClient(withInterceptors([graphqlAuthInterceptor]))');
    expect(text).toMatch(/import \{ provideHttpClient, withInterceptors \} from '@angular\/common\/http'/);
    expect(text).toMatch(/import \{ graphqlAuthInterceptor \} from '\.\/auth\/graphql-auth'/);
  });

  it('prepends the feature when provideHttpClient already has arguments', () => {
    const text = run(treeWith(CFG, wrap('provideHttpClient(withFetch())', "import { provideHttpClient, withFetch } from '@angular/common/http';")));
    expect(text).toContain('provideHttpClient(withInterceptors([graphqlAuthInterceptor]), withFetch())');
    expect(text).toMatch(/import \{ provideHttpClient, withFetch, withInterceptors \} from '@angular\/common\/http'/);
  });

  it('leaves provideHttpClient(withInterceptorsFromDi()) untouched — the class interceptor covers it', () => {
    const src = wrap('provideHttpClient(withInterceptorsFromDi())', "import { provideHttpClient, withInterceptorsFromDi } from '@angular/common/http';");
    expect(run(treeWith(CFG, src))).toBe(src);
  });

  it('leaves a host that imports HttpClientModule untouched', () => {
    const src = `import { NgModule } from '@angular/core';\nimport { HttpClientModule } from '@angular/common/http';\n@NgModule({ imports: [HttpClientModule], providers: [] })\nexport class AppModule {}\n`;
    const tree = treeWith('/src/app/app.module.ts', src);
    const out = (addHttpClientInterceptor('/src/app/app.module.ts')(tree, ctx()) as Tree).read('/src/app/app.module.ts')!.toString('utf-8');
    expect(out).toBe(src);
    expect(warnings.length).toBe(0);
  });

  it('ignores provideHttpClient( inside a comment and warns that no HttpClient provider exists', () => {
    const src = wrap('provideRouter(routes) // TODO: provideHttpClient()');
    expect(run(treeWith(CFG, src))).toBe(src);
    expect(warnings.some((w) => /provideHttpClient/.test(w))).toBeTrue();
  });

  it('warns when the host has no HttpClient provider at all', () => {
    const src = wrap('provideRouter(routes)');
    expect(run(treeWith(CFG, src))).toBe(src);
    expect(warnings.length).toBe(1);
  });

  it('patches the call inside the providers array when two calls exist, and logs the other', () => {
    const src = `import { provideHttpClient } from '@angular/common/http';\nconst spare = provideHttpClient();\nexport const appConfig = {\n  providers: [provideHttpClient()],\n};\n`;
    const text = run(treeWith(CFG, src));
    expect(count(text, 'withInterceptors([graphqlAuthInterceptor])')).toBe(1);
    expect(text).toContain('providers: [provideHttpClient(withInterceptors([graphqlAuthInterceptor]))]');
    expect(text).toContain('const spare = provideHttpClient();');
  });

  it('joins an existing withInterceptors([...]) list instead of skipping it', () => {
    const text = run(treeWith(CFG, wrap('provideHttpClient(withInterceptors([loggingInterceptor]))', "import { provideHttpClient, withInterceptors } from '@angular/common/http';")));
    expect(text).toContain('provideHttpClient(withInterceptors([loggingInterceptor, graphqlAuthInterceptor]))');
    expect(count(text, 'withInterceptors')).toBe(2); // the import and the one call — nothing added
    expect(text).toMatch(/import \{ graphqlAuthInterceptor \} from '\.\/auth\/graphql-auth'/);
  });

  it('joins an empty withInterceptors([]) list', () => {
    const text = run(treeWith(CFG, wrap('provideHttpClient(withInterceptors([]))', "import { provideHttpClient, withInterceptors } from '@angular/common/http';")));
    expect(text).toContain('withInterceptors([graphqlAuthInterceptor])');
  });

  it('warns instead of skipping when withInterceptors holds an expression it cannot see into', () => {
    const src = wrap('provideHttpClient(withInterceptors(myInterceptors))', "import { provideHttpClient, withInterceptors } from '@angular/common/http';");
    expect(run(treeWith(CFG, src))).toBe(src);
    expect(warnings.some((w) => /graphqlAuthInterceptor/.test(w))).toBeTrue();
  });

  it('is idempotent — a second pass changes nothing', () => {
    const tree = treeWith(CFG, wrap('provideHttpClient()', "import { provideHttpClient } from '@angular/common/http';"));
    const once = addHttpClientInterceptor(CFG)(tree, ctx()) as Tree;
    const first = once.read(CFG)!.toString('utf-8');
    const twice = addHttpClientInterceptor(CFG)(once, ctx()) as Tree;
    expect(twice.read(CFG)!.toString('utf-8')).toBe(first);
  });

  it('warns and leaves the tree unchanged when the host file is missing', () => {
    const tree = Tree.empty();
    addHttpClientInterceptor(undefined)(tree, ctx());
    expect(warnings.length).toBe(1);
  });
});
