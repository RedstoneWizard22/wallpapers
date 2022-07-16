"""
Used to generate README.md in this repo. You should provide the location of a
local copy of the files in my mega drive as a second argument. (This is needed
to generate the thumbnails, without downloading every single file using the
mega API)

You will need to use linux and have imagemagik installed

See also data.json :)
"""

from mega.crypto import base64_to_a32, base64_url_decode, decrypt_attr, decrypt_key
from typing import Tuple, TypedDict
from pathlib import Path
import subprocess
import requests
import json
import sys
import re

# Mega folder where wallpapers lie
REMOTE_URL = "https://mega.nz/folder/Wp100Qba#wff2p5XcQe8xH7jWeLm1rg"

# Where to put generated thumbnails
THUMBNAIL_FOLDER = "./.github/thumbnails"

# Resolution (x axis) for thumbnails
THUMBNAIL_RESOLUTION = 1280

# In which order should artist's links be displayed
# (if an item is not in this list it will be placed at the end)
LINK_PRIORITY = ["pixiv", "deviantart", "artstation", "website", "twitter"]

# README content to insert before the catalogue
README_TOP = f"""
# Wallpapers

Hello, and welcome to my wallpapers repo! This is a collection of my favourite wallpapers, AI upscaled, desnoised and converted to png.

Actually, this repo contains no wallpapers, they're all on my [mega drive]({REMOTE_URL}). Since using git to store hundreds of 4k pngs is suboptimal. What it does contain is a complete catalogue of said drive with links to the original soruces and artists that made them.

Have fun exploring :D

Ps for upscaling software, see [Tools I use](#tools-i-use) at the bottom of this README :)
""".strip()

# README content to insert after the catalogue
README_BOTTOM = """
<br />

## Tools I use

### Upscaling/denoising

#### [waifu2x](https://github.com/nagadomi/waifu2x)

The waifu2x upscaler is easy to install and comes with a set of models by default. I actually use this rewrite: [waifu2x-ncnn-vulkan](https://github.com/nihui/waifu2x-ncnn-vulkan) from the [AUR](https://aur.archlinux.org/packages/waifu2x-ncnn-vulkan). Though sometimes it doesn't produce great results with any of the models.

#### [ESRGAN](https://github.com/JoeyBallentine/ESRGAN)

I found the ESRGAN upscaler to be far more flexible, as there are a large number of models available. [upscale.wiki](https://upscale.wiki/wiki/Main_Page) explains how to install and use ESRGAN, and has a large model database. Which model to use really depends on your input image, and is mostly trial and error. I found the following useful:

From [upscale.wiki model database](https://upscale.wiki/wiki/Model_Database):

- 4x-UltraSharp
- 4x-AnimeSharp
- sudo_RealESRGAN2x_3.332.758_G.pth
- SS Anti Alias 9x

From [NMKD's models](https://nmkd.de/?esrgan):

- YandeRe (v2 and v4)
- YandereNeo
- Jaywreck3-Lite


### Color correction

#### [color-matcher](https://github.com/hahnec/color-matcher)

Allows you to transfer color across images, handy for automatic color correction

### Others

#### [imagemagik](https://imagemagick.org/)

The `convert` command lets me convert between jpg and png, and resize images from the command line

#### [gimp](https://www.gimp.org/)

I use it for light image editing if needed.

#### Reverse image search

I use both [google images](https://images.google.com) and [tineye](https://tineye.com) to track down the original artist if they are unknown
""".strip()

# See: https://stackoverflow.com/questions/64488709/how-can-i-list-the-contents-of-a-mega-public-folder-by-its-shared-url-using-meg/68639204#68639204
# And also: https://github.com/odwyersoftware/mega.py/issues/10
def get_content_of_shared_folder(url: str) -> list[Tuple[str, str]]:
    """
    Get the contents of a shared public mega folder

    Args:
        url (str): public folder url

    Returns:
        list[Tuple[str, str]]: list of (file_name, node_id) tuples
    """
    contents = []

    def get_nodes_in_shared_folder(root_folder: str) -> dict:
        data = [{"a": "f", "c": 1, "ca": 1, "r": 1}]
        response = requests.post(
            "https://g.api.mega.co.nz/cs",
            params={"id": 0, "n": root_folder},  # self.sequence_num
            data=json.dumps(data),
        )
        json_resp = response.json()
        return json_resp[0]["f"]

    def parse_folder_url(url: str) -> Tuple[str, str]:
        "Returns (public_handle, key) if valid. If not returns None."
        REGEXP1 = re.compile(
            r"mega.[^/]+/folder/([0-z-_]+)#([0-z-_]+)(?:/folder/([0-z-_]+))*"
        )
        REGEXP2 = re.compile(
            r"mega.[^/]+/#F!([0-z-_]+)[!#]([0-z-_]+)(?:/folder/([0-z-_]+))*"
        )
        m = re.search(REGEXP1, url)
        if not m:
            m = re.search(REGEXP2, url)
        if not m:
            print("Not a valid URL")
            return None
        root_folder = m.group(1)
        key = m.group(2)
        # You may want to use m.groups()[-1]
        # to get the id of the subfolder
        return (root_folder, key)

    def decrypt_node_key(key_str: str, shared_key: str) -> Tuple[int, ...]:
        encrypted_key = base64_to_a32(key_str.split(":")[1])
        return decrypt_key(encrypted_key, shared_key)

    root_folder, shared_enc_key = parse_folder_url(url)
    shared_key = base64_to_a32(shared_enc_key)
    nodes = get_nodes_in_shared_folder(root_folder)
    for node in nodes:
        key = decrypt_node_key(node["k"], shared_key)
        if node["t"] == 0:  # Is a file
            k = (key[0] ^ key[4], key[1] ^ key[5], key[2] ^ key[6], key[3] ^ key[7])
        elif node["t"] == 1:  # Is a folder
            k = key
        attrs = decrypt_attr(base64_url_decode(node["a"]), k)
        file_name = attrs["n"]
        file_id = node["h"]

        contents.append((file_name, file_id))

    return contents


class ParsedResult(TypedDict):
    artwork: str
    artist: str
    resolution: str


def parse_filename(fname: str) -> ParsedResult:
    """Parses a filename in the form $ARTWORK-by-$ARTIST-$RESOLUTION.png,
    returning a dict with name, artist and resolution entries
    """
    try:
        split_by = fname.removesuffix(".png").split("-by-")

        if len(split_by) == 1:
            # Artist is unknown :c
            artist = "unknown"
            artwork, resolution = split_by[0].rsplit("-", 1)
        else:
            artwork = split_by[0]
            artist, resolution = split_by[1].rsplit("-", 1)

        return {
            "artist": artist,
            "artwork": artwork,
            "resolution": resolution,
        }
    except Exception as e:
        print(
            f"ERROR: Failed to parse {fname}, is it int the form `$ARTWORK-by-$ARTIST-$RESOLUTION.png`?"
        )
        raise e


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("ERROR: Please provide path of local copy of mega files as a parameter")
        exit(1)

    local = Path(sys.argv[1]).expanduser()

    if not local.is_dir():
        print(f"ERROR: Provided path {local} is not a directory")
        exit(1)

    # Find all of the local wallpaper files
    localwalls = [f.name for f in local.glob("*") if f.suffix == ".png"]

    # Find all of the remote wallpaper files, and make a dict mapping
    # file name to node id
    remote_contents = get_content_of_shared_folder(REMOTE_URL)
    remotewalls = []
    fname_to_nodeid = {}
    for t in remote_contents:
        if t[0].endswith(".png"):
            fname_to_nodeid[t[0]] = t[1]
            remotewalls.append(t[0])

    # make sure the local and remote copies are synced
    for fname in remotewalls:
        if fname not in localwalls:
            print(f"ERROR: {fname} exists in the mega drive, but not in the local copy")
    for fname in localwalls:
        if fname not in remotewalls:
            print(f"ERROR: {fname} exists in the local copy, but not in the mega drive")

    # Generate the thumbnails
    thumbnail_path = Path(THUMBNAIL_FOLDER).expanduser()
    existing_thumbnails = [
        f.name for f in thumbnail_path.glob("*") if f.suffix == ".jpg"
    ]
    for fname in localwalls:
        fname_jpg = fname.replace(".png", ".jpg")
        if fname_jpg not in existing_thumbnails:
            print(f"INFO: Generating thumbnail for {fname}")
            subprocess.call(
                [
                    "convert",
                    str(local / fname),
                    "-resize",
                    str(THUMBNAIL_RESOLUTION),
                    str(thumbnail_path / fname_jpg),
                ]
            )

    # Load the datafile found in my repo
    # This contains links, full names of artists etc
    f = open("./data.json")
    datafile = json.load(f)
    f.close()

    ## Now I will generate all the data I need to generate the readme!

    class ArtworkData(TypedDict):
        name: str
        fname: str
        resolution: str
        # Path to the thumbnail file
        thumbnail: str
        # Link to the file in my mega drive
        upscaledurl: str
        # Link to the original artwork source
        sourceurl: str

    class ArtistData(TypedDict):
        # Formatted name. e.g. "Moe Wanders" not "moe-wanders"
        name: str
        # List (site_name, url) ordered by LINK_PRIORITY
        links: list[Tuple[str, str]]
        # '
        artworks: list[ArtworkData]

    data: dict[str, ArtistData] = {}
    total_artworks = 0

    for fname in localwalls:
        info = parse_filename(fname)
        artist = info["artist"]
        artwork = info["artwork"]
        resolution = info["resolution"]
        if info["artist"] not in data:
            mydata = datafile["artists"][artist]

            name = mydata["name"]

            links = []
            for linkname in LINK_PRIORITY:
                if linkname in mydata["links"]:
                    links.append((linkname, mydata["links"][linkname]))
            for linkname, linkurl in mydata["links"].items():
                if linkname not in mydata["links"]:
                    links.append((linkname, linkurl))

            data[artist] = {"name": name, "links": links, "artworks": []}

        data[artist]["artworks"].append(
            {
                "name": artwork,
                "fname": fname,
                "resolution": resolution,
                "thumbnail": str(
                    Path(THUMBNAIL_FOLDER) / fname.replace(".png", ".jpg")
                ),
                "upscaledurl": f"{REMOTE_URL}/file/{fname_to_nodeid[fname]}",
                "sourceurl": datafile["artists"][artist]["artworks"][artwork],
            }
        )
        total_artworks += 1

    # Alright, now to the fun part - generating the README
    readme = README_TOP
    readme += f"""
## Catalogue
    
> Note previews are 720p jpg to save bandwidth, click the mega link (or filename) for full resolution. On mega the images may take some time to load (They are ~10MB each)

```
~ Totals ~

Wallpapers:  {total_artworks}
Artists:     {len(data)}
```
"""

    # I want to write artists by artwork count
    for k, v in reversed(sorted(data.items(), key=lambda x: len(x[1]["artworks"]))):
        readme += f"<details><summary><b>{v['name']}</b></summary>\n\n"

        readme += f"### links\n\n"
        for sitename, url in v["links"]:
            readme += f"- [{sitename}]({url})\n"

        readme += f"\n### gallery\n\n"
        for artwork in v["artworks"]:
            readme += f"#### [{artwork['fname']}]({artwork['upscaledurl']})\n\n"
            readme += f"[![{artwork['fname']}]({artwork['thumbnail']})]({artwork['upscaledurl']})\n"
            # readme += f'<img alt="{artwork["fname"]}" src="{artwork["thumbnail"]}" width="{THUMBNAIL_RESOLUTION}" />'
            readme += f"([original source]({artwork['sourceurl']})) ([mega link]({artwork['upscaledurl']}))\n\n"

        readme += f"\n<br />\n</details>\n"

    readme += "\n\n" + README_BOTTOM

    # Write out the README!
    f = open("./README.md", "w")
    print(readme, file=f)
    f.close()

    print("DONE :D")
