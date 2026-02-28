import os
import zipfile


def zip_directory(source_dir, arc_prefix, zipf):
    # Walk a folder and add files to the archive under arc_prefix
    for root, _, files in os.walk(source_dir):
        for file in files:
            file_path = os.path.join(root, file)
            # compute archive name relative to the source directory, then prepend prefix
            relpath = os.path.relpath(file_path, source_dir)
            arcname = os.path.join(arc_prefix, relpath) if arc_prefix else relpath
            zipf.write(file_path, arcname)


def build_modpack(sources, output_filename):
    # keep track of paths already added so we don't duplicate when a file
    # exists in both the root and the minecraft/ subdirectory.
    seen = set()
    with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for src, prefix in sources:
            if os.path.isdir(src):
                for root, _, files in os.walk(src):
                    for file in files:
                        file_path = os.path.join(root, file)
                        relpath = os.path.relpath(file_path, src)
                        arcname = os.path.join(prefix, relpath) if prefix else relpath
                        if arcname in seen:
                            continue
                        seen.add(arcname)
                        zipf.write(file_path, arcname)
            elif os.path.isfile(src):
                # single file (e.g. manifest) – use prefix as output name or the
                # basename if no prefix supplied
                arcname = prefix or os.path.basename(src)
                if arcname not in seen:
                    seen.add(arcname)
                    zipf.write(src, arcname)
            else:
                print(f"warning: source path '{src}' does not exist, skipping")


if __name__ == "__main__":
    # operate relative to the script's own directory, not the current
    # working directory.  this prevents the "mods folder imported a directory
    # too high" problem when someone runs the script from inside
    # minecraft/ or another subfolder.
    base = os.path.dirname(os.path.abspath(__file__))
    def rel(path):
        return os.path.join(base, path)

    # ensure we have a simple instance.cfg as some launchers (Prism) look for
    # it rather than mmc-pack.json.  If the user has provided one already it
    # will be left unchanged; otherwise build one from the minecraft version
    # contained in mmc-pack.json (if present).
    inst_cfg = rel("instance.cfg")
    if not os.path.exists(inst_cfg):
        mc_version = None
        try:
            import json
            with open(rel("mmc-pack.json"), "r", encoding="utf-8") as f:
                data = json.load(f)
            for comp in data.get("components", []):
                if comp.get("uid") == "net.minecraft":
                    mc_version = comp.get("version")
                    break
        except Exception:
            pass
        with open(inst_cfg, "w", encoding="utf-8") as f:
            f.write("[Instance]\n")
            f.write("name=Modpack\n")
            if mc_version:
                f.write(f"mcVersion={mc_version}\n")

    sources = [
        # include the MultiMC/Prism manifest so launchers recognise the pack
        (rel("mmc-pack.json"), ""),
        # include instance.cfg for compatibility with launchers that expect it
        (inst_cfg, ""),

        # everything below gets placed inside the minecraft/ folder so that an
        # imported pack produces the same layout as a real Prism/MultiMC
        # instance.  `rel("mods")` is there to support users who keep a
        # standalone mods/ directory next to the instance rather than inside it.
        (rel("mods"), "minecraft/mods"),
        (rel("minecraft/mods"), "minecraft/mods"),
        (rel("minecraft/config"), "minecraft/config"),
        (rel("minecraft/scripts"), "minecraft/scripts"),
        (rel("minecraft/groovy"), "minecraft/groovy"),
        (rel("minecraft/resourcepacks"), "minecraft/resourcepacks"),
    ]

    output_zip = rel("build/modpack-latest.zip")

    if not os.path.exists(rel("build")):
        os.makedirs(rel("build"))

    build_modpack(sources, output_zip)
    print(f"Modpack zipped successfully: {output_zip}")