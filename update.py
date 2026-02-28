"""Download the actual jar files described by the metadata under
`metadata/mods/`.

The repository should contain only the TOML index files (one per mod); the
jars themselves are downloaded on demand by this script.  The script also
removes any leftover jars that are not listed in the index (unless the
`force_inclusion` function returns True).

This is essentially the same approach used by the Dimension‑Gateway pack.
"""

import os
import pathlib
import dataclasses
import json
import urllib.request
import urllib.parse
import sys

# TOML library: use built-in tomllib on Python>=3.11, otherwise try tomli.
# Initialize the name to None so we can detect failures.
tomllib = None
try:
    import tomllib as tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except Exception:
        # any failure here leaves tomllib None; attempt to install tomli
        import subprocess, sys
        print("tomllib/tomli not found or import error; installing tomli...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tomli"])
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except Exception:
            tomllib = None

if tomllib is None:
    raise RuntimeError("Cannot import tomllib or tomli; update.py requires a TOML parser.")


@dataclasses.dataclass
class DownloadFile:
    name: str
    filename: str
    project_id: str  # can be CurseForge numeric id or a direct URL

    @property
    def url(self):
        # if project_id looks like a URL just use it directly
        if self.project_id.startswith("http"):
            return self.project_id
        # otherwise treat as CurseForge file ID
        first, last = self.project_id[:-3], self.project_id[-3:]
        return (
            f"https://edge.forgecdn.net/files/{first}/{last}/"
            f"{urllib.parse.quote(self.filename)}"
        )


def force_inclusion(file: str) -> bool:
    """Return True if the given file should be kept even if it's not in the index.

    This is useful for mods that are not available on CurseForge and thus won't
    have a file-id to include in the metadata.  You can hardcode any special
    cases here.
    """
    return file == "example-mod.jar"


def import_prism_index(index_file: pathlib.Path, index_path: pathlib.Path):
    """Convert a Prism-generated index to toml files in metadata/mods.

    The index may be a single JSON file (`minecraft/mods/.index`) or a
    directory containing TOML metadata (as produced by some launchers/pack
    managers).  The function will ingest whichever format it finds.
    """
    if not index_file.exists():
        return

    # if index_file is a directory (or symlink to one), treat its children as already-correct TOML
    # (use os.path.isdir because pathlib.is_dir may return False for symlinks on some systems)
    if os.path.isdir(index_file):
        for child in index_file.iterdir():
            if child.suffix.lower() != ".toml":
                continue
            dest = index_path / child.name
            if dest.exists():
                continue
            dest.write_bytes(child.read_bytes())
        return

    # otherwise assume it's JSON metadata
    try:
        with open(index_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"failed to load prism index: {e}")
        return
    entries = data if isinstance(data, list) else data.get("mods", [])
    for e in entries:
        fname = e.get("filename") or e.get("fileName")
        if not fname:
            continue
        dest = index_path / (fname + ".toml")
        if dest.exists():
            continue
        name = e.get("name", fname)
        # guess a curseforge file-id from a few common spots
        cfid = (
            e.get("curseforge_project_id")
            or e.get("curseforgeProjectID")
            or e.get("fileID")
            or (e.get("update", {}) or {}).get("curseforge", {}).get("file-id")
        )
        with open(dest, "w", encoding="utf-8") as out:
            out.write(f'name = "{name}"\n')
            out.write(f'filename = "{fname}"\n')
            if cfid:
                out.write("\n[update.curseforge]\n")
                out.write(f"file-id = {cfid}\n")


def main():
    instance = pathlib.Path(__file__).parent
    mods_path = instance / "minecraft" / "mods"
    index_path = instance / "metadata" / "mods"

    # if the launcher has produced a .index file, import it first
    import_prism_index(mods_path / ".index", index_path)

    skipped = 0
    downloaded = []
    needed_files = set()
    deleted_files = []

    def confirm(prompt: str) -> bool:
        """Return True if the user agrees, or auto-yes in non-interactive mode."""
        if not sys.stdin.isatty():
            # running in CI/no terminal, assume yes
            print(prompt + " (auto-confirmed)")
            return True
        return input(prompt).lower() != "n"

    # read each metadata file and determine which jar we need
    for fn in os.listdir(index_path):
        if not fn.endswith(".toml"):
            continue
        with open(index_path / fn, "rb") as fd:
            data = tomllib.load(fd)

        mn = data.get("filename")
        if not mn:
            continue
        needed_files.add(mn)
        if (mods_path / mn).exists():
            skipped += 1
        else:
            cf_section = data.get("update", {}).get("curseforge", {})
            cfid = cf_section.get("file-id")
            mr_section = data.get("update", {}).get("modrinth", {})
            mr_url = mr_section.get("url")
            if cfid:
                downloaded.append(
                    DownloadFile(data.get("name", "?"), mn, str(cfid))
                )
            elif mr_url:
                downloaded.append(
                    DownloadFile(data.get("name", "?"), mn, mr_url)
                )
            else:
                print(f"warning: no curseforge/modrinth info for '{mn}', skipping download")

    # find extraneous jars
    if mods_path.exists():
        for fn in os.listdir(mods_path):
            if not fn.endswith(".jar") or fn in needed_files:
                continue
            if force_inclusion(fn):
                continue
            deleted_files.append(fn)

    if not deleted_files and not downloaded:
        print("All mods are already downloaded!")
        return

    if skipped:
        print(f"Skipping {skipped} mods as they're already installed.")
    if deleted_files:
        if confirm(f"{len(deleted_files)} files need to be deleted. Continue? (Y/n) "):
            for f in deleted_files:
                os.unlink(mods_path / f)
    if downloaded:
        if confirm(f"{len(downloaded)} files need to be downloaded. Continue? (Y/n) "):
            mods_path.mkdir(parents=True, exist_ok=True)
            for df in downloaded:
                print(f"Downloading {df.name}...")
                try:
                    with urllib.request.urlopen(df.url) as req:
                        with open(mods_path / df.filename, "wb") as output:
                            while chunk := req.read(524288):
                                output.write(chunk)
                except urllib.error.HTTPError as e:
                    print(f"failed to download {df.name}: HTTP {e.code} {e.reason}")
                except Exception as e:
                    print(f"error downloading {df.name}: {e}")

    print("All done!")


if __name__ == "__main__":
    main()
