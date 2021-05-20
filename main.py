import os, requests, shutil, json, glob, urllib.request, argparse, sys
from sanitize_filename import sanitize
import urllib.request
from tqdm import tqdm
from dotenv import load_dotenv
from mpegdash.parser import MPEGDASHParser
from mpegdash.nodes import Descriptor
from mpegdash.utils import (parse_attr_value, parse_child_nodes,
                            parse_node_value, write_attr_value,
                            write_child_node, write_node_value)
from utils import extract_kid
from vtt_to_srt import convert

course_id = None
header_bearer = None
download_dir = "%s\out_dir" % os.getcwd()
working_dir = "%s\working_dir" % os.getcwd(
)  # set the folder to download segments for DRM videos
retry = 3
home_dir = os.getcwd()
keyfile_path = "%s\keyfile.json" % os.getcwd()
dl_assets = False
dl_captions = False
skip_lectures = False
caption_locale = "en"
quality = None  # None will download the best possible
valid_qualities = [144, 360, 480, 720, 1080]

if not os.path.exists(working_dir):
    os.makedirs(working_dir)

if not os.path.exists(download_dir):
    os.makedirs(download_dir)

#Get the keys
with open(keyfile_path, 'r') as keyfile:
    keyfile = keyfile.read()
keyfile = json.loads(keyfile)
"""
@author Jayapraveen
"""


def durationtoseconds(period):
    #Duration format in PTxDxHxMxS
    if (period[:2] == "PT"):
        period = period[2:]
        day = int(period.split("D")[0] if 'D' in period else 0)
        hour = int(period.split("H")[0].split("D")[-1] if 'H' in period else 0)
        minute = int(
            period.split("M")[0].split("H")[-1] if 'M' in period else 0)
        second = period.split("S")[0].split("M")[-1]
        print("Total time: " + str(day) + " days " + str(hour) + " hours " +
              str(minute) + " minutes and " + str(second) + " seconds")
        total_time = float(
            str((day * 24 * 60 * 60) + (hour * 60 * 60) + (minute * 60) +
                (int(second.split('.')[0]))) + '.' +
            str(int(second.split('.')[-1])))
        return total_time

    else:
        print("Duration Format Error")
        return None


def download_media(filename, url, lecture_working_dir, epoch=0):
    if (os.path.isfile(filename)):
        print("Segment already downloaded.. skipping..")
    else:
        media = requests.get(url, stream=True)
        media_length = int(media.headers.get("content-length"))
        if media.status_code == 200:
            if (os.path.isfile(filename)
                    and os.path.getsize(filename) >= media_length):
                print("Segment already downloaded.. skipping write to disk..")
            else:
                try:
                    pbar = tqdm(total=media_length,
                                initial=0,
                                unit='B',
                                unit_scale=True,
                                desc=filename)
                    with open(f"{lecture_working_dir}\\{filename}",
                              'wb') as video_file:
                        for chunk in media.iter_content(chunk_size=1024):
                            if chunk:
                                video_file.write(chunk)
                                pbar.update(1024)
                    pbar.close()
                    print("Segment downloaded: " + filename)
                    return False  #Successfully downloaded the file
                except:
                    print(
                        "Connection error: Reattempting download of segment..")
                    download_media(filename, url, lecture_working_dir,
                                   epoch + 1)

            if os.path.getsize(filename) >= media_length:
                pass
            else:
                print("Segment is faulty.. Redownloading...")
                download_media(filename, url, lecture_working_dir, epoch + 1)
        elif (media.status_code == 404):
            print("Probably end hit!\n", url)
            return True  #Probably hit the last of the file
        else:
            if (epoch > retry):
                exit("Error fetching segment, exceeded retry times.")
            print("Error fetching segment file.. Redownloading...")
            download_media(filename, url, lecture_working_dir, epoch + 1)


"""
@author Jayapraveen
"""


def cleanup(path):
    leftover_files = glob.glob(path + '/*.mp4', recursive=True)
    mpd_files = glob.glob(path + '/*.mpd', recursive=True)
    leftover_files = leftover_files + mpd_files
    for file_list in leftover_files:
        try:
            os.remove(file_list)
        except OSError:
            print(f"Error deleting file: {file_list}")


"""
@author Jayapraveen
"""


def mux_process(video_title, lecture_working_dir, outfile):
    if os.name == "nt":
        command = f"ffmpeg -y -i \"{lecture_working_dir}\\decrypted_audio.mp4\" -i \"{lecture_working_dir}\\decrypted_video.mp4\" -acodec copy -vcodec copy -fflags +bitexact -map_metadata -1 -metadata title=\"{video_title}\" -metadata creation_time=2020-00-00T70:05:30.000000Z \"{outfile}\""
    else:
        command = f"nice -n 7 ffmpeg -y -i \"{lecture_working_dir}\\decrypted_audio.mp4\" -i \"{lecture_working_dir}\\decrypted_video.mp4\" -acodec copy -vcodec copy -fflags +bitexact -map_metadata -1 -metadata title=\"{video_title}\" -metadata creation_time=2020-00-00T70:05:30.000000Z \"{outfile}\""
    os.system(command)


"""
@author Jayapraveen
"""


def decrypt(kid, filename, lecture_working_dir):
    try:
        key = keyfile[kid.lower()]
    except KeyError as error:
        exit("Key not found")
    if (os.name == "nt"):
        os.system(
            f"mp4decrypt --key 1:{key} \"{lecture_working_dir}\\encrypted_{filename}.mp4\" \"{lecture_working_dir}\\decrypted_{filename}.mp4\""
        )
    else:
        os.system(
            f"nice -n 7 mp4decrypt --key 1:{key} \"{lecture_working_dir}\\encrypted_{filename}.mp4\" \"{lecture_working_dir}\\decrypted_{filename}.mp4\""
        )


"""
@author Jayapraveen
"""


def handle_irregular_segments(media_info, video_title, lecture_working_dir,
                              output_path):
    no_segment, video_url, video_init, video_extension, no_segment, audio_url, audio_init, audio_extension = media_info
    download_media("video_0.seg.mp4", video_init, lecture_working_dir)
    video_kid = extract_kid(f"{lecture_working_dir}\\video_0.seg.mp4")
    print("KID for video file is: " + video_kid)
    download_media("audio_0.seg.mp4", audio_init, lecture_working_dir)
    audio_kid = extract_kid(f"{lecture_working_dir}\\audio_0.seg.mp4")
    print("KID for audio file is: " + audio_kid)
    for count in range(1, no_segment):
        video_segment_url = video_url.replace("$Number$", str(count))
        audio_segment_url = audio_url.replace("$Number$", str(count))
        video_status = download_media(
            f"video_{str(count)}.seg.{video_extension}", video_segment_url,
            lecture_working_dir)
        audio_status = download_media(
            f"audio_{str(count)}.seg.{audio_extension}", audio_segment_url,
            lecture_working_dir)
        os.chdir(lecture_working_dir)
        if (video_status):
            if os.name == "nt":
                video_concat_command = "copy /b " + "+".join([
                    f"video_{i}.seg.{video_extension}"
                    for i in range(0, count)
                ]) + " encrypted_video.mp4"
                audio_concat_command = "copy /b " + "+".join([
                    f"audio_{i}.seg.{audio_extension}"
                    for i in range(0, count)
                ]) + " encrypted_audio.mp4"
            else:
                video_concat_command = "cat " + " ".join([
                    f"video_{i}.seg.{video_extension}"
                    for i in range(0, count)
                ]) + " > encrypted_video.mp4"
                audio_concat_command = "cat " + " ".join([
                    f"audio_{i}.seg.{audio_extension}"
                    for i in range(0, count)
                ]) + " > encrypted_audio.mp4"
            os.system(video_concat_command)
            os.system(audio_concat_command)
            decrypt(video_kid, "video", lecture_working_dir)
            decrypt(audio_kid, "audio", lecture_working_dir)
            os.chdir(home_dir)
            mux_process(video_title, lecture_working_dir, output_path)
            break


"""
@author Jayapraveen
"""


def manifest_parser(mpd_url):
    video = []
    audio = []
    manifest = requests.get(mpd_url).text
    with open("manifest.mpd", 'w') as manifest_handler:
        manifest_handler.write(manifest)
    mpd = MPEGDASHParser.parse("./manifest.mpd")
    running_time = durationtoseconds(mpd.media_presentation_duration)
    for period in mpd.periods:
        for adapt_set in period.adaptation_sets:
            print("Processing " + adapt_set.mime_type)
            content_type = adapt_set.mime_type
            if quality and content_type == "video/mp4":
                print(adapt_set.representations[0].height, quality)
                repr = next((x for x in adapt_set.representations
                             if x.height == quality), None)
                if not repr:
                    qualities = []
                    for rep in adapt_set.representations:
                        qualities.append(rep.height)
                    print(quality, qualities)
                    if quality < qualities[0]:
                        # they want a lower quality than whats available
                        repr = adapt_set.representations[0]  # Lowest Quality
                    elif quality > qualities[-1]:
                        # they want a higher quality than whats available
                        repr = adapt_set.representations[-1]  # Max Quality
                    print(
                        "> Could not find video with requested quality, falling back to closest!"
                    )
                    print("> Using quality of %s" % repr.height)
                else:
                    print("> Found MPD representation with quality %s" %
                          repr.height)
            else:
                repr = adapt_set.representations[-1]  # Max Quality
                print("> Using max quality of %s" % repr.height)
            for segment in repr.segment_templates:
                if (segment.duration):
                    print("Media segments are of equal timeframe")
                    segment_time = segment.duration / segment.timescale
                    total_segments = running_time / segment_time
                else:
                    print("Media segments are of inequal timeframe")

                    approx_no_segments = round(
                        running_time /
                        6) + 10  # aproximate of 6 sec per segment
                    print("Expected No of segments:", approx_no_segments)
                    if (content_type == "audio/mp4"):
                        segment_extension = segment.media.split(".")[-1]
                        audio.append(approx_no_segments)
                        audio.append(segment.media)
                        audio.append(segment.initialization)
                        audio.append(segment_extension)
                    elif (content_type == "video/mp4"):
                        segment_extension = segment.media.split(".")[-1]
                        video.append(approx_no_segments)
                        video.append(segment.media)
                        video.append(segment.initialization)
                        video.append(segment_extension)
    return video + audio


"""
@author Puyodead1
"""


def download(url, path, filename):
    """
    @param: url to download file
    @param: path place to put the file
    @oaram: filename used for progress bar
    """
    file_size = int(requests.head(url).headers["Content-Length"])
    if os.path.exists(path):
        first_byte = os.path.getsize(path)
    else:
        first_byte = 0
    if first_byte >= file_size:
        return file_size
    header = {"Range": "bytes=%s-%s" % (first_byte, file_size)}
    pbar = tqdm(total=file_size,
                initial=first_byte,
                unit='B',
                unit_scale=True,
                desc=filename)
    res = requests.get(url, headers=header, stream=True)
    res.raise_for_status()
    with (open(path, 'ab')) as f:
        for chunk in res.iter_content(chunk_size=1024):
            if chunk:
                f.write(chunk)
                pbar.update(1024)
    pbar.close()
    return file_size


def process_caption(caption,
                    lecture_index,
                    lecture_title,
                    lecture_dir,
                    tries=0):
    filename = f"%s. %s_%s.%s" % (lecture_index, sanitize(lecture_title),
                                  caption.get("locale_id"), caption.get("ext"))
    filename_no_ext = f"%s. %s_%s" % (lecture_index, sanitize(lecture_title),
                                      caption.get("locale_id"))
    filepath = f"%s\\%s" % (lecture_dir, filename)

    if os.path.isfile(filepath):
        print("> Captions '%s' already downloaded." % filename)
    else:
        print(f"> Downloading captions: '%s'" % filename)
        try:
            download(caption.get("url"), filepath, filename)
        except Exception as e:
            if tries >= 3:
                print(
                    f"> Error downloading captions: {e}. Exceeded retries, skipping."
                )
                return
            else:
                print(
                    f"> Error downloading captions: {e}. Will retry {3-tries} more times."
                )
                process_caption(caption, lecture_index, lecture_title,
                                lecture_dir, tries + 1)
        if caption.get("ext") == "vtt":
            try:
                print("> Converting captions to SRT format...")
                convert(lecture_dir, filename_no_ext)
                print("> Caption conversion complete.")
                os.remove(filepath)
            except Exception as e:
                print(f"> Error converting captions: {e}")


def process_lecture(lecture, lecture_index, lecture_path, lecture_dir):
    lecture_title = lecture["title"]
    lecture_asset = lecture["asset"]
    if not skip_lectures:
        if lecture_asset["media_license_token"] == None:
            # not encrypted
            media_sources = lecture_asset["media_sources"]
            if quality:  # if quality is specified, try to find the requested quality
                lecture_url = next(
                    (x["src"]
                     for x in media_sources if x["label"] == str(quality)),
                    media_sources[0]["src"]
                )  # find the quality requested or return the best available
            else:
                lecture_url = media_sources[0][
                    "src"]  # best quality is the first index

            if not os.path.isfile(lecture_path):
                try:
                    download(lecture_url, lecture_path, lecture_title)
                except Exception as e:
                    # We could add a retry here
                    print(f"> Error downloading lecture: {e}. Skipping...")
            else:
                print(f"> Lecture '%s' is already downloaded, skipping..." %
                      lecture_title)
        else:
            # encrypted
            print(f"> Lecture '%s' has DRM, attempting to download" %
                  lecture_title)
            lecture_working_dir = "%s\%s" % (
                working_dir, lecture_asset["id"]
            )  # set the folder to download ephemeral files
            media_sources = lecture_asset["media_sources"]
            if not os.path.exists(lecture_working_dir):
                os.mkdir(lecture_working_dir)
            if not os.path.isfile(lecture_path):
                mpd_url = next((x["src"] for x in media_sources
                                if x["type"] == "application/dash+xml"), None)
                if not mpd_url:
                    print(
                        "> Couldn't find dash url for lecture '%s', skipping...",
                        lecture_title)
                    return
                base_url = mpd_url.split("index.mpd")[0]
                media_info = manifest_parser(mpd_url)
                handle_irregular_segments(media_info, lecture_title,
                                          lecture_working_dir, lecture_path)
                cleanup(lecture_working_dir)
            else:
                print("> Lecture '%s' is already downloaded, skipping..." %
                      lecture_title)

    # process assets
    if dl_assets:
        assets = []
        all_assets = lecture["supplementary_assets"]
        for asset in all_assets:
            if asset["asset_type"] == "File":
                assets.append(asset)
                asset_filename = asset["filename"]
                download_url = next((x["file"]
                                     for x in asset["download_urls"]["File"]
                                     if x["label"] == "download"), None)
                if download_url:
                    try:
                        download(download_url,
                                 f"%s\\%s" % (lecture_dir, asset_filename),
                                 asset_filename)
                    except Exception as e:
                        print(
                            f"> Error downloading lecture asset: {e}. Skipping"
                        )
                        continue
        print("> Found %s assets for lecture '%s'" %
              (len(assets), lecture_title))

    # process captions
    if dl_captions:
        captions = []
        for caption in lecture_asset.get("captions"):
            if not isinstance(caption, dict):
                continue
            if caption.get("_class") != "caption":
                continue
            download_url = caption.get("url")
            if not download_url or not isinstance(download_url, str):
                continue
            lang = (caption.get("language") or caption.get("srclang")
                    or caption.get("label")
                    or caption.get("locale_id").split("_")[0])
            ext = "vtt" if "vtt" in download_url.rsplit(".", 1)[-1] else "srt"
            if caption_locale == "all" or caption_locale == lang:
                captions.append({
                    "language": lang,
                    "locale_id": caption.get("locale_id"),
                    "ext": ext,
                    "url": download_url
                })

        for caption in captions:
            process_caption(caption, lecture_index, lecture_title, lecture_dir)


def parse(data):
    course_dir = f"%s\\%s" % (download_dir, course_id)
    if not os.path.exists(course_dir):
        os.mkdir(course_dir)
    chapters = []
    lectures = []

    for obj in data:
        if obj["_class"] == "chapter":
            obj["lectures"] = []
            chapters.append(obj)
        elif obj["_class"] == "lecture" and obj["asset"][
                "asset_type"] == "Video":
            try:
                chapters[-1]["lectures"].append(obj)
            except IndexError:
                # This is caused by there not being a starting chapter
                lectures.append(obj)
                lecture_index = lectures.index(obj) + 1
                lecture_path = f"%s\\%s. %s.mp4" % (course_dir, lecture_index,
                                                    sanitize(obj["title"]))
                process_lecture(obj, lecture_index, lecture_path, download_dir)

    for chapter in chapters:
        chapter_dir = f"%s\\%s. %s" % (course_dir, chapters.index(chapter) + 1,
                                       sanitize(chapter["title"]))
        if not os.path.exists(chapter_dir):
            os.mkdir(chapter_dir)

        for lecture in chapter["lectures"]:
            lecture_index = chapter["lectures"].index(lecture) + 1
            lecture_path = f"%s\\%s. %s.mp4" % (chapter_dir, lecture_index,
                                                sanitize(lecture["title"]))
            process_lecture(lecture, lecture_index, lecture_path, chapter_dir)
    print("\n\n\n\n\n\n\n\n=====================")
    print("All downloads completed for course!")
    print("=====================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Udemy Downloader')
    parser.add_argument(
        "-d",
        "--debug",
        dest="debug",
        action="store_true",
        help="Use test_data.json rather than fetch from the udemy api.",
    )
    parser.add_argument(
        "-b",
        "--bearer",
        dest="bearer_token",
        type=str,
        help="The Bearer token to use",
    )
    parser.add_argument(
        "-c",
        "--course-id",
        dest="course_id",
        type=str,
        help="The ID of the course to download",
    )
    parser.add_argument(
        "-q",
        "--quality",
        dest="quality",
        type=int,
        help="Download specific video quality. (144, 360, 480, 720, 1080)",
    )
    parser.add_argument(
        "-l",
        "--lang",
        dest="lang",
        type=str,
        help="The language to download for captions (Default is en)",
    )
    parser.add_argument(
        "--skip-lectures",
        dest="skip_lectures",
        action="store_true",
        help="If specified, lectures won't be downloaded.",
    )
    parser.add_argument(
        "--download-assets",
        dest="download_assets",
        action="store_true",
        help="If specified, lecture assets will be downloaded.",
    )
    parser.add_argument(
        "--download-captions",
        dest="download_captions",
        action="store_true",
        help="If specified, captions will be downloaded.",
    )

    args = parser.parse_args()
    if args.download_assets:
        dl_assets = True
    if args.lang:
        caption_locale = args.lang
    if args.download_captions:
        dl_captions = True
    if args.skip_lectures:
        skip_lectures = True
    if args.quality:
        if not args.quality in valid_qualities:
            print("Invalid quality specified! %s" % quality)
            sys.exit(1)
        else:
            quality = args.quality

    load_dotenv()
    if args.bearer_token:
        header_bearer = f"Bearer %s" % args.bearer_token
    else:
        header_bearer = f"Bearer %s" % os.getenv("UDEMY_BEARER")
    if args.course_id:
        course_id = args.course_id
    else:
        course_id = os.getenv("UDEMY_COURSE_ID")

    if not course_id:
        print("> Missing Course ID!")
        sys.exit(1)
    if not header_bearer:
        print("> Missing Bearer Token!")
        sys.exit(1)

    print(f"> Using course ID {course_id}")

    if args.debug:
        # this is for development purposes so we dont need to make tons of requests when testing
        # course data json is just stored and read from a file
        with open("test_data.json", encoding="utf8") as f:
            data = json.loads(f.read())["results"]
            parse(data)
    else:
        print("Fetching Course data, this may take a minute...")
        r = requests.get(
            f"https://udemy.com/api-2.0/courses/{course_id}/cached-subscriber-curriculum-items?fields[asset]=results,title,external_url,time_estimation,download_urls,slide_urls,filename,asset_type,captions,media_license_token,course_is_drmed,media_sources,stream_urls,body&fields[chapter]=object_index,title,sort_order&fields[lecture]=id,title,object_index,asset,supplementary_assets,view_html&page_size=10000"
            .format(course_id),
            headers={
                "Authorization": header_bearer,
                "x-udemy-authorization": header_bearer
            })
        if r.status_code == 200:
            print("Course data retrieved!")
            data = r.json()
            parse(data["results"])
        else:
            print("An error occurred while trying to fetch the course data! " +
                  r.text)