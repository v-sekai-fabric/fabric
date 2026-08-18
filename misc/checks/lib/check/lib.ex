# The parts every concern needs, and nothing that belongs to one of them.
#
# Each concern is its own module under lib/check/ and each states its own checks. What lives here is what
# would otherwise exist in seven copies: reading the manifest, asking GitHub, knowing where
# the workspace root is, the policy tables that more than one concern consults, and the
# runner that prints a result and decides the exit code.
#
# A check is a map:
#
#     %{label: "...", kind: :local | :network, run: fn ctx -> [failure, ...] end,
#       break: fn ctx -> ctx end}
#
# `run` returns a list of failures, empty when the invariant holds. `break` returns a
# context that must make `run` fail -- the negative control, without which a gate certifies
# nothing. Python held these as module globals that the self-test assigned to; here the
# context is a value passed in, so a control cannot leak out of the check it belongs to.

defmodule Check.Lib do
  @moduledoc "Shared reading, shared policy, and the runner."

  require Record

  Record.defrecord(:xmlElement, Record.extract(:xmlElement, from_lib: "xmerl/include/xmerl.hrl"))

  Record.defrecord(
    :xmlAttribute,
    Record.extract(:xmlAttribute, from_lib: "xmerl/include/xmerl.hrl")
  )

  @doc """
  The repository root, found by looking for it rather than by counting directories.

  A compiled module's `__DIR__` is where its source sat when it was built, and a mix task
  runs from wherever the caller was standing, so neither is a reliable base. Both are tried
  as starting points and each walks up until it finds the manifest beside the README, which
  is the pair that identifies this repository and nothing else.
  """
  def root do
    [File.cwd!(), __DIR__]
    |> Enum.find_value(&climb_to_root/1)
    |> case do
      nil -> raise "cannot find default.xml beside README.md above #{File.cwd!()} or #{__DIR__}"
      found -> found
    end
  end

  defp climb_to_root(start) do
    start
    |> Path.expand()
    |> Stream.iterate(&Path.dirname/1)
    |> Enum.take_while(&(&1 != "/"))
    |> Enum.concat(["/"])
    |> Enum.find(fn dir ->
      File.exists?(Path.join(dir, "default.xml")) and File.exists?(Path.join(dir, "README.md"))
    end)
  end

  def manifest_path, do: Path.join(root(), "default.xml")
  def readme_path, do: Path.join(root(), "README.md")

  @doc """
  Where the children sit.

  `repo init` puts this repository in `.repo/manifests` and the children two levels above
  it. A plain clone has them beside it. Both layouts are real, so this asks which one it is
  in rather than assuming.
  """
  def workspace_root do
    r = root()

    if Path.basename(r) == "manifests" and Path.basename(Path.dirname(r)) == ".repo" do
      r |> Path.dirname() |> Path.dirname()
    else
      r
    end
  end

  @doc "Collapse whitespace so a line wrap in the README cannot defeat a check."
  def flat(text), do: String.replace(text, ~r/\s+/, " ")

  # --- the manifest ------------------------------------------------------------------

  @doc """
  `{default_attrs, remotes, projects}` from the manifest text.

  xmerl is stdlib, so this parses the XML rather than pattern-matching it. A manifest that
  stops being well formed should fail loudly here, not silently match fewer projects.
  """
  def parse_manifest(text) do
    {doc, _} = :xmerl_scan.string(String.to_charlist(text), quiet: true)
    children = xmlElement(doc, :content)

    remotes =
      children
      |> elements_named(:remote)
      |> Map.new(fn e -> {attr(e, :name), attr(e, :fetch)} end)

    default =
      case elements_named(children, :default) do
        [e | _] -> %{remote: attr(e, :remote), revision: attr(e, :revision), sync_j: attr(e, :"sync-j")}
        [] -> nil
      end

    projects =
      children
      |> elements_named(:project)
      |> Enum.map(fn e ->
        name = attr(e, :name)
        remote = attr(e, :remote)
        fetch = Map.get(remotes, remote)

        %{
          name: name,
          # `path` is optional and defaults to the name, which is what repo does.
          path: attr(e, :path) || name,
          remote: remote,
          revision: attr(e, :revision),
          org: org_of(fetch),
          url: "#{fetch}/#{name}.git"
        }
      end)

    {default, remotes, projects}
  end

  def projects(text), do: parse_manifest(text) |> elem(2)

  def org_of(nil), do: ""
  def org_of(url), do: url |> String.trim_trailing("/") |> String.split("/") |> List.last()

  defp elements_named(children, want) do
    Enum.filter(children, fn
      e when Record.is_record(e, :xmlElement) -> xmlElement(e, :name) == want
      _ -> false
    end)
  end

  defp attr(element, want) do
    element
    |> xmlElement(:attributes)
    |> Enum.find_value(fn a ->
      if xmlAttribute(a, :name) == want, do: to_string(xmlAttribute(a, :value))
    end)
  end

  # --- asking GitHub -----------------------------------------------------------------

  @doc """
  One `gh api` call, returning stdout or nil. The unit the pool below maps over.

  stderr is captured rather than inherited. Asking for the Pages URL of a repository that
  serves none is a 404, which is the answer and not a fault, and letting gh print it puts
  a dozen lines of noise above a result that says everything passed.
  """
  def gh(args) do
    case System.cmd("gh", ["api" | args], stderr_to_stdout: true) do
      {out, 0} -> String.trim(out)
      _ -> nil
    end
  catch
    :error, _ -> nil
  end

  @doc """
  Run many `gh api` calls at once, keyed however the caller keys them.

  Serially the network checks took 181 s, nearly all of it waiting. Sixteen at a time,
  which is what `<default sync-j="16">` already asks repo for against the same host, so
  this is not a new number to tune.

  What belongs here is only what a checkout cannot answer. A repository's licence, its
  revisions and its current name are all on disk once `repo sync` has run, and asking
  GitHub for them is a round trip to learn something already local.
  """
  def gh_many(calls) do
    calls
    |> Task.async_stream(fn {k, args} -> {k, gh(args)} end,
      max_concurrency: 16,
      timeout: 120_000,
      on_timeout: :kill_task
    )
    |> Enum.map(fn
      {:ok, pair} -> pair
      {:exit, _} -> nil
    end)
    |> Enum.reject(&is_nil/1)
    |> Map.new()
  end

  @doc "Run a shell command, returning `{output, status}`. Used where a check reads git."
  def cmd(exe, args, opts \\ []) do
    System.cmd(exe, args, Keyword.merge([stderr_to_stdout: true], opts))
  catch
    :error, _ -> {"", 127}
  end

  # --- policy, consulted by more than one concern -------------------------------------

  def our_remote, do: "v-sekai-multiplayer-fabric"

  def readme_max, do: 40

  @doc """
  A mirror's README is upstream's. Editing it forks a document this project does not own,
  so the limit does not reach one. Each entry states the evidence rather than an opinion:
  two carry GitHub's fork flag, and the third carries upstream's own README.
  """
  def mirrors do
    %{
      # This project owns the Windows builds here and none of the code, so the README is
      # upstream's to write. GitHub carries the fork flag for both of these.
      "datasource-foundationdb" => "apple/foundationdb",
      "idtx-flow" => "Immersive-Data-Center-Management/idtx-flow",
      # No fork flag, and the README is still upstream's: it opens "# Godot Engine" and
      # links godotengine.org nineteen times.
      "entities-godot" => "godotengine/godot"
    }
  end

  @doc """
  The one entry GitHub does not back. A fork made by pushing an existing history rather
  than by pressing the button carries no fork flag and no parent, so the evidence has to be
  stated instead of fetched -- and stating it is the point: an exemption with a reason can
  be argued with, and a list nobody can check is a list that grows.
  """
  def unflagged_mirrors do
    %{
      "entities-godot" =>
        "no fork flag; its README opens '# Godot Engine' and links godotengine.org nineteen times"
    }
  end

  @doc """
  The organisations this project may write to. Everything else in the manifest is read: its
  code is checked out, built against and cited, and nothing here pushes a commit, opens a
  pull request or files an issue against it.

  The list is short on purpose. A repository we can technically write to is not a repository
  we are entitled to change, and admin rights are a poor proxy for permission -- five
  V-Sekai repositories, one on taskweft and one on meshula were renamed from here on
  exactly that reasoning, which is the mistake this exists to stop repeating.

  `taskweft` is on the list because it is ours, stated by its owner rather than inferred
  from the admin bit that is sitting right there. That is the distinction the paragraph
  above is about: what put it here is the sentence, not the permission.

  `sinew-mocap`, `weftspun`, `lattice-world-weft`, `weftfit`, `chibifire-characters` and
  `chibifire-stages` are here on the same sentence from the same owner. No project in this
  manifest sits on any of them yet, so none of those entries decides anything today. They
  are written now so that the day a project arrives from one, the answer is already on the
  page instead of being read off the admin bit in a hurry.
  """
  @spec allowed_orgs() :: [String.t()]
  def allowed_orgs do
    [
      "v-sekai-multiplayer-fabric",
      "v-sekai-fire",
      "fire",
      "taskweft",
      "sinew-mocap",
      "weftspun",
      "lattice-world-weft",
      "weftfit",
      "chibifire-characters",
      "chibifire-stages"
    ]
  end

  @doc """
  Projects outside those organisations, each with whose they are. An entry here is a
  statement that the repository is read-only to this project; a project from an unlisted
  organisation fails the check rather than being quietly assumed one way or the other.
  """
  def read_only do
    %{
      "cassie" => "the academic CASSIE project's Unity application, V-Sekai's branch of it",
      "cassie-data" => "the sketch dataset recorded for the CASSIE paper",
      "entities-model-explorer" => "V-Sekai's 3D model viewer",
      "interactor-sketch" => "V-Sekai's Godot CASSIE work",
      "transport-xr-grid" => "V-Sekai's VR interaction tool",
      "LabRCSF" => "Nick Porcino's reference skeleton; we have no admin on it either"
    }
  end

  @doc """
  Names that are not this repository's to change, so recomposition gives way rather than
  forcing a rename. `path` and `name` are independent in repo -- a project sits on its side
  either way -- so recomposition is a convention this repository imposes and these are where
  it costs more than it is worth. Each entry states its reason.
  """
  def fixed_names do
    %{
      "cassie" => "the academic CASSIE project's Unity application; the name is the paper's",
      "cassie-data" => "the sketch dataset recorded for that paper",
      "idtx-flow" => "Immersive-Data-Center-Management/idtx-flow, mirrored",
      "LabRCSF" => "meshula/LabRCSF; we have no admin on it, so we cannot rename it",
      # A repository name is also a published address when it serves Pages, and GitHub does
      # not redirect a Pages URL on rename. This one was renamed to contract-manuals and
      # every published RFD link 404'd until it was renamed back.
      "multiplayer-fabric-manuals" => "it publishes GitHub Pages, whose URL contains the name"
    }
  end

  @doc "The projects whose documents and files are this project's to write."
  def ours(projects) do
    Enum.filter(projects, &(&1.remote == our_remote() and not Map.has_key?(mirrors(), &1.name)))
  end

  # --- children's documents ------------------------------------------------------------

  @child_docs ~w(README.md CLAUDE.md AGENTS.md)

  @doc """
  `[{project_path, doc_name, text}]` for our children, or the injected fixture.

  Checks that scan the children read files rather than text passed in, so a breakage that
  edits the manifest or the README cannot reach them. Every document they read comes
  through here, and `ctx.docs` replaces the result. That is what makes their negative
  controls real: the control injects a defective document and the check must go red.
  """
  def child_docs(ctx, projects) do
    case ctx[:docs] do
      nil ->
        ws = workspace_root()

        for p <- ours(projects), name <- @child_docs, path = Path.join([ws, p.path, name]),
            File.exists?(path) do
          {p.path, name, File.read!(path)}
        end

      injected ->
        injected
    end
  end

  # --- the runner ------------------------------------------------------------------

  @doc """
  Run `checks` against argv and exit.

  `--fast` is the checkout, `--slow` is the network. Everything a `repo sync` already put
  on disk is answered from disk, so fast is the larger half and the one that runs on every
  commit; slow asks GitHub only about repository settings a clone cannot carry.

  A deferred check prints as deferred rather than vanishing, because a silent skip reads
  exactly like a pass.
  """
  def run(checks, argv) do
    self_test? = "--self-test" in argv
    only_local? = "--fast" in argv or "--local-only" in argv
    only_network? = "--slow" in argv

    ctx = %{
      mtext: File.read!(manifest_path()),
      rtext: File.read!(readme_path())
    }

    selected =
      Enum.reject(checks, fn c ->
        (only_local? and c.kind == :network) or (only_network? and c.kind == :local)
      end)

    deferred = if only_local?, do: Enum.filter(checks, &(&1.kind == :network)), else: []

    failed = Enum.count(selected, fn c -> report(c.label, c.run.(ctx)) end)
    failed = failed + if self_test?, do: self_test(selected, ctx), else: 0

    scanned_children(ctx)
    for c <- deferred, do: IO.puts("defer  #{c.label}  (runs at pre-push, not skipped)")
    IO.puts("\n#{failed} failing check(s)")
    exit_with(failed)
  end

  # A document check with no children on disk passes because it saw nothing, which reads
  # exactly like passing because everything was clean. Say which it was.
  defp scanned_children(ctx) do
    seen =
      ctx
      |> child_docs(projects(ctx.mtext))
      |> MapSet.new(fn {path, _name, _text} -> path end)
      |> MapSet.size()

    tail =
      if seen == 0,
        do: "; a bare clone has none, and they hold where the workspace is",
        else: ""

    IO.puts("note   the document checks scanned #{seen} children#{tail}")
  end

  defp report(label, []) do
    IO.puts("ok    #{label}")
    false
  end

  defp report(label, bad) do
    IO.puts("FAIL  #{label}")
    for b <- bad, do: IO.puts("        #{b}")
    true
  end

  # Each check paired with an edit that must break it. A gate never shown to fail certifies
  # nothing -- see the Checks section of CLAUDE.md.
  defp self_test(selected, ctx) do
    IO.puts("\nnegative controls (each check must fail on broken input):")

    Enum.count(selected, fn c ->
      broken = c.break.(ctx)

      cond do
        broken == ctx ->
          IO.puts("FAIL  #{c.label}: breakage pattern no longer matches; control is dead")
          true

        c.run.(broken) == [] ->
          IO.puts("FAIL  #{c.label} PASSED on broken input — it is decoration")
          true

        true ->
          IO.puts("ok    #{c.label} fails on broken input")
          false
      end
    end)
  end

  @doc "Replace text in the manifest, for a control that perturbs what the check reads."
  def break_manifest(ctx, old, new), do: %{ctx | mtext: String.replace(ctx.mtext, old, new)}

  @doc "Replace text in the README, for the same reason."
  def break_readme(ctx, old, new), do: %{ctx | rtext: String.replace(ctx.rtext, old, new)}

  defp exit_with(0), do: :ok
  defp exit_with(_), do: System.halt(1)
end
