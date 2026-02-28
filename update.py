import os, pathlib, dataclasses, json, urllib.request, urllib.parse, sys

tomllib = None
try: import tomllib as tomllib
except ImportError:
    try: import tomli as tomllib
    except Exception:
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "tomli"])
        try: import tomli as tomllib
        except Exception: tomllib = None

if tomllib is None:
    raise RuntimeError("Cannot import tomllib or tomli")

@dataclasses.dataclass
class DownloadFile:
    name: str; filename: str; project_id: str
    @property
    def url(self):
        if self.project_id.startswith("http"): return self.project_id
        first, last = self.project_id[:-3], self.project_id[-3:]
        return f"https://edge.forgecdn.net/files/{first}/{last}/{urllib.parse.quote(self.filename)}"

def force_inclusion(file: str) -> bool: return file == "example-mod.jar"

def import_prism_index(index_file: pathlib.Path, index_path: pathlib.Path):
    if not index_file.exists(): return
    if os.path.isdir(index_file):
        for child in index_file.iterdir():
            if child.suffix.lower() != ".toml": continue
            dest = index_path / child.name
            if dest.exists(): continue
            dest.write_bytes(child.read_bytes())
        return
    try:
        with open(index_file, "r", encoding="utf-8") as f: data = json.load(f)
    except Exception as e:
        print(f"failed to load prism index: {e}"); return
    entries = data if isinstance(data, list) else data.get("mods", [])
    for e in entries:
        fname = e.get("filename") or e.get("fileName")
        if not fname: continue
        dest = index_path / (fname + ".toml")
        if dest.exists(): continue
        name = e.get("name", fname)
        cfid = (
            e.get("curseforge_project_id")
            or e.get("curseforgeProjectID")
            or e.get("fileID")
            or (e.get("update", {}) or {}).get("curseforge", {}).get("file-id")
        )
        with open(dest, "w", encoding="utf-8") as out:
            out.write(f'name = "{name}"\nfilename = "{fname}"\n')
            if cfid:
                out.write("\n[update.curseforge]\nfile-id = {cfid}\n")

def confirm(prompt: str) -> bool:
    if not sys.stdin.isatty(): print(prompt+" (auto-confirmed)"); return True
    return input(prompt).lower() != "n"

def main():
    instance = pathlib.Path(__file__).parent
    mods_path = instance / "minecraft" / "mods"
    index_path = instance / "metadata" / "mods"
    import_prism_index(mods_path / ".index", index_path)
    skipped=0; downloaded=[]; needed_files=set(); deleted_files=[]
    for fn in os.listdir(index_path):
        if not fn.endswith(".toml"): continue
        with open(index_path / fn, "rb") as fd: data = tomllib.load(fd)
        mn = data.get("filename")
        if not mn: continue
        needed_files.add(mn)
        if (mods_path / mn).exists(): skipped+=1
        else:
            cf_section = data.get("update", {}).get("curseforge", {})
            cfid = cf_section.get("file-id")
            mr_section = data.get("update", {}).get("modrinth", {})
            mr_url = mr_section.get("url")
            if cfid: downloaded.append(DownloadFile(data.get("name","?"),mn,str(cfid)))
            elif mr_url: downloaded.append(DownloadFile(data.get("name","?"),mn,mr_url))
            else: print(f"warning: no curseforge/modrinth info for '{mn}', skipping download")
    if mods_path.exists():
        for fn in os.listdir(mods_path):
            if not fn.endswith(".jar") or fn in needed_files: continue
            if force_inclusion(fn): continue
            deleted_files.append(fn)
    if not deleted_files and not downloaded: print("All mods are already downloaded!"); return
    if skipped: print(f"Skipping {skipped} mods as they're already installed.")
    if deleted_files and confirm(f"{len(deleted_files)} files need to be deleted. Continue? (Y/n) "):
        for f in deleted_files: os.unlink(mods_path / f)
    if downloaded and confirm(f"{len(downloaded)} files need to be downloaded. Continue? (Y/n) "):
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
