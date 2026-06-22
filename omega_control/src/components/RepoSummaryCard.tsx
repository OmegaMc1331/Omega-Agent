export type RepoSummaryView = {
  id?: string | null;
  workspace_path: string;
  is_git_repo: boolean;
  languages: string[];
  frameworks: string[];
  package_managers: string[];
  test_commands: string[];
  build_commands: string[];
  entrypoints: string[];
  config_files: string[];
  updated_at?: string | null;
};

export function RepoSummaryCard({ repo }: { repo: RepoSummaryView | null }) {
  if (!repo) {
    return <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4 text-sm text-zinc-500">Aucun scan repo disponible.</section>;
  }
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-stone-100">Repository</div>
          <div className="mt-1 break-all text-xs text-zinc-500">{repo.workspace_path}</div>
        </div>
        <span className="rounded-full border border-white/10 bg-black/10 px-2 py-1 text-xs text-zinc-400">{repo.is_git_repo ? 'git repo' : 'no git'}</span>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <Row label="Languages" values={repo.languages} />
        <Row label="Frameworks" values={repo.frameworks} />
        <Row label="Package managers" values={repo.package_managers} />
        <Row label="Tests" values={repo.test_commands} />
        <Row label="Build" values={repo.build_commands} />
        <Row label="Entrypoints" values={repo.entrypoints} />
      </div>
      {repo.config_files.length > 0 && (
        <div className="mt-3">
          <div className="mb-2 text-xs uppercase text-zinc-600">Config files</div>
          <div className="flex flex-wrap gap-2">
            {repo.config_files.slice(0, 20).map((file) => <span key={file} className="rounded-full bg-white/[0.05] px-2 py-1 text-xs text-zinc-400">{file}</span>)}
          </div>
        </div>
      )}
    </section>
  );
}

function Row({ label, values }: { label: string; values: string[] }) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/10 p-3">
      <div className="text-xs uppercase text-zinc-600">{label}</div>
      <div className="mt-1 text-sm text-zinc-300">{values.length ? values.join(', ') : 'none'}</div>
    </div>
  );
}
