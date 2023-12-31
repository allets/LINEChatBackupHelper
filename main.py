import argparse
import csv
import logging
import os
import re
import sys
from enum import IntEnum, unique

import filetype

LOG_DIR = f"{os.getcwd()}/log"
if not os.path.isdir(LOG_DIR):
    os.mkdir(LOG_DIR)

LOGGING_FORMAT = "%(asctime)s %(levelname)s: %(message)s"
logging.basicConfig(level=logging.DEBUG,
                    handlers=[
                        logging.StreamHandler(sys.stdout),
                        logging.FileHandler(f"{LOG_DIR}/backup_line.log", "w", "utf-8")
                    ],
                    format=LOGGING_FORMAT)

CHATROOM_FIELD_NAMES = ["ID", "Name", "Status"]


class DataPrintable:
    def __str__(self):
        return f"<{self.__class__.__name__}\n" \
               f"    {str(self.__dict__)}\n" \
               f">"


@unique
class ChatroomStatus(IntEnum):
    JOINED = 1
    EXITED = 2


class ChatroomRecord(DataPrintable):
    def __init__(self, id, name: str, status: ChatroomStatus = ChatroomStatus.JOINED):
        self.id = id
        self.name = name
        self.status = status


def chatroom_raw_record_to_chatroom_record(raw) -> ChatroomRecord:
    record = ChatroomRecord(raw["ID"],
                            raw["Name"],
                            ChatroomStatus(int(raw["Status"])))
    return record


class ChatroomWriter:

    def __init__(self, filepath):
        self.filepath = filepath

    def __enter__(self):
        logging.debug(f"open: {self.filepath}")
        self._file = open(self.filepath, mode="w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=CHATROOM_FIELD_NAMES, quoting=csv.QUOTE_ALL)
        self._writer.writeheader()
        return self

    def __exit__(self, e_type, e_value, traceback):
        if not e_type:
            logging.debug(f"close: {self.filepath}")
            self._file.close()
        else:
            logging.error(f"\nException type: {e_type}"
                          f"\nException value: {e_value}"
                          f"\nTraceback: {traceback}\n")

    def create(self, record: ChatroomRecord):
        self._writer.writerow(
            {"ID": record.id,
             "Name": record.name,
             "Status": record.status.value})


class ChatroomReader:
    def __init__(self, filepath):
        self.filepath = filepath

    def __enter__(self):
        logging.debug(f"open: {self.filepath}")
        self._file = open(self.filepath, newline="", encoding="utf-8")
        self._reader = csv.DictReader(self._file, quoting=csv.QUOTE_ALL)
        return self

    def __exit__(self, e_type, e_value, traceback):
        if not e_type:
            logging.debug(f"close: {self.filepath}")
            self._file.close()
        else:
            logging.error(f"\nException type: {e_type}"
                          f"\nException value: {e_value}"
                          f"\nTraceback: {traceback}\n")

    def _get_reader(self):
        if self._reader.line_num > 0:
            self._file.seek(0)
            next(self._reader)  # skip header
        return self._reader

    def list_record(self):
        records = []
        for row in self._get_reader():
            record = chatroom_raw_record_to_chatroom_record(row)
            records.append(record)

        return records


def determine_chatroom_status(str) -> ChatroomStatus:
    status = ChatroomStatus.EXITED if str == "被退出" else ChatroomStatus.JOINED
    return status


def determine_chatroom_status_text(status: ChatroomStatus) -> str:
    text = "被退出" if status == ChatroomStatus.EXITED else ""
    return text


def parse_chatroom_dir_name(fn) -> ChatroomRecord:
    if len(fn) == 33:
        record = ChatroomRecord(fn, "")

    else:
        arr = fn.split("-")
        record = ChatroomRecord(arr[-1], arr[-2])

        if len(arr) == 3:
            record.status = determine_chatroom_status(arr[0])

    return record


def gen_chatroom_dir_name(chatroom: ChatroomRecord):
    status_text = determine_chatroom_status_text(chatroom.status)
    if status_text:
        return f"{status_text}-{chatroom.name}-{chatroom.id}"
    else:
        return f"{chatroom.name}-{chatroom.id}"


def extract_chatroom_id_name_mappings(chats_dir_path, output_path):
    """
    Extract mappings of chat room ID and name.

    Prerequisites:
        Chat room directories are in your backup directory of `/sdcard/Android/data/jp.naver.line.android/files/chats`.

        You should rename chat room directory as `xxx-ID` or `被退出-xxx-ID`,
        e.g., "家有兩寶-c3337f8e15f2f1d79f69fd2b0575476b6"
        or "被退出-旅行團-c7acf23b06ad3e4c029dc5ef6d6e88444".

        The ID is generated by LINE and starts with "u", "c" or "r" followed by 32 hex digits.

        The term "xxx" is provided BY YOU manually and is a meaningful name of the chat room.

        The term "被退出" is provided BY YOU manually and means that you are exited.
        Default status of chat room is joined.


    Args:
        chats_dir_path: your backup directory path of `/sdcard/Android/data/jp.naver.line.android/files/chats`
        output_path: The CSV file saves the mappings.
    """
    if not os.path.isdir(chats_dir_path):
        logging.error(f"is not a directory: {chats_dir_path}")
        return

    filenames = [fn for fn in os.listdir(chats_dir_path) if os.path.isdir(f"{chats_dir_path}/{fn}")]

    with ChatroomWriter(output_path) as chatroom:
        for fn in filenames:
            record = parse_chatroom_dir_name(fn)
            chatroom.create(record)


def prefix_chatroom_dir_name(chats_dir_path, chatroom_db_path):
    """
    Prefix the name of the chat room to ID.

    Prerequisites:
        see :func:`extract_chatroom_id_name_mappings`.

    Args:
        chats_dir_path: your backup directory path of `/sdcard/Android/data/jp.naver.line.android/files/chats`
        chatroom_db_path: The CSV file saves the mappings.
    """
    with ChatroomReader(chatroom_db_path) as chatroom:
        records = chatroom.list_record()

        chatrooms = {}
        for record in records:
            chatrooms[record.id] = record

    if len(chatrooms) == 0:
        return

    filenames = [fn for fn in os.listdir(chats_dir_path) if os.path.isdir(f"{chats_dir_path}/{fn}")]
    for fn in filenames:
        chatroom = chatrooms.get(fn)
        if chatroom is None or not chatroom.name:
            continue

        new_fn = gen_chatroom_dir_name(chatroom)
        os.rename(f"{chats_dir_path}/{fn}",
                  f"{chats_dir_path}/{new_fn}")


def diff_chatroom(old_chat_dir_path, new_chat_dir_path):
    if not os.path.isdir(old_chat_dir_path) or not os.path.isdir(new_chat_dir_path):
        logging.error(f"is not a directory: `{old_chat_dir_path}`\n  or `{new_chat_dir_path}")
        return

    old_filenames = [fn for fn in os.listdir(old_chat_dir_path) if os.path.isdir(f"{old_chat_dir_path}/{fn}")]
    new_filenames = [fn for fn in os.listdir(new_chat_dir_path) if os.path.isdir(f"{new_chat_dir_path}/{fn}")]

    old_ids = set()
    for fn in old_filenames:
        record = parse_chatroom_dir_name(fn)
        old_ids.add(record.id)

    new_ids = set()
    for fn in new_filenames:
        record = parse_chatroom_dir_name(fn)
        new_ids.add(record.id)

    diff_list = new_ids - old_ids

    return diff_list


def move_images_to_dir(msg_dir_path, thumbnail_names, thumbnail_dir_name, image_dir_name):
    not_existed_img_amount = 0

    thumbnail_dir_path = f"{msg_dir_path}/{thumbnail_dir_name}"
    if not os.path.isdir(thumbnail_dir_path):
        os.mkdir(thumbnail_dir_path)

    image_dir_path = f"{msg_dir_path}/{image_dir_name}"
    if not os.path.isdir(image_dir_path):
        os.mkdir(image_dir_path)

    for image_name in thumbnail_names:
        os.rename(f"{msg_dir_path}/{image_name}.thumb",
                  f"{thumbnail_dir_path}/{image_name}.thumb")

        if os.path.exists(f"{msg_dir_path}/{image_name}"):
            os.rename(f"{msg_dir_path}/{image_name}",
                      f"{image_dir_path}/{image_name}")

        else:
            not_existed_img_amount += 1
            logging.debug(f"image Not exists: {image_name}")

    if not_existed_img_amount > 0:
        logging.debug(f"Not existed image amount= {not_existed_img_amount}/{len(thumbnail_names)}"
                      f"\n    msg_dir_path= {msg_dir_path}")


def move_original_images_to_dir(msg_dir_path, original_image_names, original_image_dir_name):
    original_image_dir_path = f"{msg_dir_path}/{original_image_dir_name}"
    if not os.path.isdir(original_image_dir_path):
        os.mkdir(original_image_dir_path)

    for image_name in original_image_names:
        os.rename(f"{msg_dir_path}/{image_name}.original",
                  f"{original_image_dir_path}/{image_name}.original")


def move_all_images_to_dir(chats_dir_path):
    if not os.path.isdir(chats_dir_path):
        logging.error(f"is not a directory: {chats_dir_path}")
        return

    chat_dir_names = [fn for fn in os.listdir(chats_dir_path) if os.path.isdir(f"{chats_dir_path}/{fn}")]
    for chat_dir_name in chat_dir_names:
        msg_dir_path = f"{chats_dir_path}/{chat_dir_name}/messages"

        thumbnail_names = []
        original_image_names = []
        for fn in os.listdir(msg_dir_path):
            if os.path.isfile(f"{msg_dir_path}/{fn}"):
                (filename_without_ext, sep, ext) = fn.rpartition(".")
                if ext == "thumb":
                    thumbnail_names.append(filename_without_ext)
                elif ext == "original":
                    original_image_names.append(filename_without_ext)

        logging.debug(f"thumbnail amount= {len(thumbnail_names)}"
                      f", original_images amount= {len(original_image_names)}"
                      f" in `{chat_dir_name}`")

        move_images_to_dir(msg_dir_path, thumbnail_names, "thumbnails", "images")
        move_original_images_to_dir(msg_dir_path, original_image_names, "original_images")


def append_file_extension(dir_path, fn, extension):
    if fn.endswith(f".{extension}"):
        return

    new_fn = f"{fn}.{extension}"

    os.rename(f"{dir_path}/{fn}",
              f"{dir_path}/{new_fn}")


def substitute_file_extension(dir_path, fn, extension):
    (filename_without_ext, sep, ext) = fn.rpartition(".")
    if filename_without_ext == "":
        new_fn = f"{fn}.{extension}"
    else:
        new_fn = f"{filename_without_ext}.{extension}"

    os.rename(f"{dir_path}/{fn}",
              f"{dir_path}/{new_fn}")


def rename_file_extension_in_dir(dir_path, extension, is_append=False):
    if not os.path.isdir(dir_path):
        logging.error(f"is not a directory: {dir_path}")
        return

    filenames = [fn for fn in os.listdir(dir_path) if os.path.isfile(f"{dir_path}/{fn}")]
    if is_append:
        for fn in filenames:
            append_file_extension(dir_path, fn, extension)

    else:
        for fn in filenames:
            substitute_file_extension(dir_path, fn, extension)


def correct_file_extension_in_dir(dir_path, excluded_extensions: list = None):
    if excluded_extensions is None:
        ext_pattern = None
    else:
        ext_pattern = f"^.+.({'|'.join(excluded_extensions)})$"

    filenames = [fn for fn in os.listdir(dir_path) if os.path.isfile(f"{dir_path}/{fn}")]

    types = set()
    for fn in filenames:
        fp = f"{dir_path}/{fn}"

        if ext_pattern is not None:
            match = re.match(ext_pattern, fn)
            if match is not None:
                excluded_ext = match.groups()[0]
                types.add(excluded_ext)
                # logging.debug(f"exclude ext `{fn}` in `{dir_path[-60:]}`")
                continue

        kind = filetype.guess(fp)
        if kind is None:
            logging.info(f"Cannot guess file type: {fp}")
            continue

        types.add(kind.extension)
        append_file_extension(dir_path, fn, kind.extension)

    logging.debug(f"types= {types} @ `{dir_path[-70:]}`")


def correct_images_file_extension(chats_dir_path):
    if not os.path.isdir(chats_dir_path):
        logging.error(f"is not a directory: {chats_dir_path}")
        return

    chat_dir_names = [fn for fn in os.listdir(chats_dir_path) if os.path.isdir(f"{chats_dir_path}/{fn}")]
    for chat_dir_name in chat_dir_names:
        msg_dir_path = f"{chats_dir_path}/{chat_dir_name}/messages"
        thumbnail_dir_path = f"{msg_dir_path}/thumbnails"
        image_dir_path = f"{msg_dir_path}/images"
        original_image_dir_path = f"{msg_dir_path}/original_images"

        rename_file_extension_in_dir(thumbnail_dir_path, "jpg", True)
        rename_file_extension_in_dir(image_dir_path, "jpg", True)
        correct_file_extension_in_dir(original_image_dir_path)
        correct_file_extension_in_dir(msg_dir_path, ["aac"])


def main():
    ap = argparse.ArgumentParser(
        description="LINE Chat Backup Helper\n"
                    "-----------------------------------------------\n"
                    "  * classify images into `thumbnails`, `images` or `original_images` folders\n"
                    "  * append file extension to file name\n"
                    "  * prefix a meaningful name to chat room folder(ID)"
                    " after extracting mappings of chat room ID and name provided BY YOU\n"
                    "  * compare chat room list with the older one",
        formatter_class=argparse.RawTextHelpFormatter, )
    ap.add_argument("-e", "--execution", required=False,
                    type=int, choices=range(1, 3),
                    help="ONLY (1) extract mappings or (2) prefix name")
    ap.add_argument("-d", "--chats-dir", required=True,
                    help="your backup directory path of `/sdcard/Android/data/jp.naver.line.android/files/chats`")
    ap.add_argument("-l", "--chatroom-db", required=False, metavar="chatroom.csv",
                    help="The CSV file saves the mappings of chat room ID and name provided BY YOU.")
    ap.add_argument("-d0", "--old-chats-dir", required=False, metavar="CHATS_DIR",
                    help="compare chat rooms in the `--chats-dir` folder with the older one")

    args = vars(ap.parse_args())
    execution = args["execution"]
    chats_dir_path = args["chats_dir"]
    chatroom_db_path = args["chatroom_db"]
    old_chats_dir_path = args["old_chats_dir"]

    logging.debug(f"\n=== console params ====================================\n"
                  f"execution= {execution}\n"
                  f"chats_dir_path= {chats_dir_path}\n"
                  f"chatroom_db_path= {chatroom_db_path}\n"
                  f"old_chats_dir_path= {old_chats_dir_path}\n"
                  f"=======================================================\n")

    chats_dir_path = os.path.expanduser(chats_dir_path)
    chatroom_db_path = os.path.expanduser(chatroom_db_path) if chatroom_db_path else chatroom_db_path
    old_chats_dir_path = os.path.expanduser(old_chats_dir_path) if old_chats_dir_path else old_chats_dir_path

    logging.debug(f"\n=== params ============================================\n"
                  f"execution= {execution}\n"
                  f"chats_dir_path= {chats_dir_path}\n"
                  f"chatroom_db_path= {chatroom_db_path}\n"
                  f"old_chats_dir_path= {old_chats_dir_path}\n"
                  f"=======================================================\n")

    if execution is None:
        logging.debug("move_all_images_to_dir")
        move_all_images_to_dir(chats_dir_path)
        correct_images_file_extension(chats_dir_path)

        if chatroom_db_path:
            prefix_chatroom_dir_name(chats_dir_path, chatroom_db_path)

        if old_chats_dir_path:
            new_chatrooms = diff_chatroom(old_chats_dir_path, chats_dir_path)
            logging.info(f"new chat rooms= {new_chatrooms}")

    elif execution == 1:
        if not chatroom_db_path:
            logging.error(f"Extracting mappings requires `--chatroom-db`.")
            return

        logging.debug("extract_chatroom_id_name_mappings")
        extract_chatroom_id_name_mappings(chats_dir_path, chatroom_db_path)

    elif execution == 2:
        if not chatroom_db_path:
            logging.error(f"Prefixing name requires `--chatroom-db`.")
            return

        logging.debug("prefix_chatroom_dir_name")
        prefix_chatroom_dir_name(chats_dir_path, chatroom_db_path)


if __name__ == '__main__':
    main()
