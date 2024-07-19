#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph
import argparse
import coloredlogs
import emoji
import html
import json
import logging
import os
import sys
from filter import Filter

logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
level_styles = {
    'debug': {'color': 'cyan'},
    'info': {'color': 'green'},
    'warning': {'color': 'yellow'},
    'error': {'color': 'red'},
    'critical': {'bold': True, 'color': 'red'},
}
formatter = coloredlogs.ColoredFormatter(
    "%(asctime)s %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
    level_styles=level_styles)
handler.setFormatter(formatter)
logger.addHandler(handler)


def unknown_type(t: str):
    raise TypeError(f"Unknown element type {t}")


class Message:
    def __init__(self, data, db: SlackDB) -> None:
        self.data = data
        self.db = db

    def _text(self, data) -> str:
        return data["text"]

    def _link(self, data) -> str:
        return data["url"]

    def _broadcast(self, data) -> str:
        return f"@{data['range']}"

    def _user(self, data) -> str:
        user = self.db.user_name(data["user_id"])
        return f"@{user}"

    def _emoji(self, data) -> str:
        emoji_str = f":{data['name']}:"
        return emoji.emojize(emoji_str) + f"[emoji {emoji_str}]"

    def _channel(self, data) -> str:
        channel_name = self.db.channel_name(data["channel_id"])
        return channel_name

    def _rich_text_element(self, data) -> str:
        parts = []
        for e in data["elements"]:
            t = e["type"]
            if t == "broadcast":
                parts.append(self._broadcast(e))
            elif t == "text":
                parts.append(self._text(e))
            elif t == "user":
                parts.append(self._user(e))
            elif t == "link":
                parts.append(self._link(e))
            elif t == "emoji":
                parts.append(self._emoji(e))
            elif t == "channel":
                parts.append(self._channel(e))
            else:
                unknown_type(t)
        return "".join(parts)

    def _rich_text_list(self, data) -> str:
        parts = []
        for e in data["elements"]:
            t = e["type"]
            if t == "rich_text_section":
                parts.append("- " + self._rich_text_element(e))
            else:
                unknown_type(t)
        return "\n".join(parts)

    def _rich_text(self, data) -> str:
        parts = []
        for e in data["elements"]:
            t = e["type"]
            if t == "rich_text_section":
                parts.append(self._rich_text_element(e))
            elif t == "rich_text_preformatted":
                parts.append(self._rich_text_element(e))
            elif t == "rich_text_quote":
                parts.append("> " + self._rich_text_element(e))
            elif t == "rich_text_list":
                parts.append(self._rich_text_list(e))
            else:
                unknown_type(t)
        return "\n".join(parts)

    def _blocks_field(self, data=None) -> str:
        if data is None:
            data = self.data
        if "blocks" not in data:
            return ""
        parts = []
        for block in data["blocks"]:
            t = block["type"]
            if t == "rich_text":
                parts.append(self._rich_text(block))
            else:
                unknown_type(t)
        return "\n".join(parts)

    def _root_field(self) -> str:
        pass

    def _subtype_field(self) -> str:
        # Parse subtype
        if "subtype" not in self.data:
            return ""
        elif self.data["subtype"] == "joiner_notification":
            return f"[{self.data['text']}]"
        elif self.data["subtype"] == "joiner_notification_for_inviter":
            user = self.db.user_name(self.data["user"])
            return f"[{user} joined group]"
        elif self.data["subtype"] == "group_join":
            if "inviter" in self.data:
                inviter = self.db.user_name(self.data["inviter"])
                return f"[joined group, invited by {inviter}]"
            else:
                return "[joined group]"
        elif self.data["subtype"] == "group_leave":
            return "[left group]"
        elif self.data["subtype"] == "channel_join":
            if "inviter" in self.data:
                inviter = self.db.user_name(self.data["inviter"])
                return f"[joined channel, invited by {inviter}]"
            else:
                return "[joined channel]"
        elif self.data["subtype"] == "group_purpose":
            return f"[Edited group purpose: {self.data['purpose']}]"
        elif self.data["subtype"] == "thread_broadcast":
            return f"[thread root] " + self._blocks_field(self.data["root"])
        elif self.data["subtype"] == "channel_name":
            user = self.db.user_name(self.data["user"])
            return f"[{user} {self.data['text']}]"
        elif self.data["subtype"] == "channel_topic":
            user = self.db.user_name(self.data["user"])
        elif self.data["subtype"] == "channel_purpose":
            user = self.db.user_name(self.data["user"])
            return f"[{user} set channel purpose: {self.data['purpose']}]"
        elif self.data["subtype"] == "bot_message":
            return ""
        elif self.data["subtype"] == "mpdm_move":
            return "" # TODO: move to new group due to member change
        else:
            raise TypeError(f"Unknown message subtype {self.data['subtype']}")

    def _file(self, data) -> str:
        if "mode" in data and data["mode"] == "tombstone":
            return "[file removed]"
        if "file_access" in data and data["file_access"] == "file_not_found":
            return "[file not found]"
        return data["name"]

    def _files_field(self) -> str:
        if "files" not in self.data:
            return ""
        files = []
        for file in self.data["files"]:
            files.append("[file] " + self._file(file))
        return "\n".join(files)

    def _message_type(self) -> str:
        subtype = self._subtype_field()
        blocks = self._blocks_field()
        files = self._files_field()
        return "\n".join(e for e in [subtype, blocks, files] if e)

    def text(self) -> str:
        if self.data["type"] == "message":
            return self._message_type()
        else:
            raise TypeError(f"Unknown message type {self.data['type']}")

    def user(self) -> str:
        return self.db.user_name(self.data["user"])

    def time(self) -> str:
        ts = float(self.data["ts"])
        date = datetime.fromtimestamp(ts)
        return date.strftime("%H:%M")

    def edited(self) -> str:
        if "edited" in self.data:
            return " [edited]"
        return ""

    def __str__(self) -> str:
        time = self.time()
        user = self.user()
        text = html.escape(self.text())
        edited = self.edited()
        return f"{time}\n{user}: {text}{edited}"

    def __repr__(self) -> str:
        return self.__str__()


class User:
    def __init__(self, data) -> None:
        self.data = data
        try:
            self.name = self.data["profile"]["real_name"]
        except Exception as e:
            print(self.data["id"])
            raise (e)
        if not self.name:
            logger.warning(f"fail to get name for user {self.data['id']}")

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return self.__str__()


class Chat:
    def __init__(self, path, name, db):
        self.path = path
        self.name = name
        self.db = db

    def parse_file(self, file) -> str:
        file_path = os.path.join(self.path, file)
        logger.debug(f"Parsing {file_path}")
        with open(file_path) as f:
            data = json.load(f)
        messages = []
        for m in data:
            try:
                messages.append(str(Message(m, self.db)))
            except Exception as e:
                print("\n\n".join(messages[-3:]))
                raise (e)
        return "\n\n".join(messages)

    def export(self, out_dir: str, force_rebuild: bool = False, dates_filter: list = None):
        logger.info(f"Exporting chat {self.name}")
        self.files = os.listdir(self.path)
        self.files.sort()
        file_path = os.path.join(out_dir, f"{self.name}.pdf")

        if os.path.exists(file_path):
            if force_rebuild:
                logger.warning(f"Overriding {file_path}")
                os.remove(file_path)
            else:
                logger.warning(f"Skip existing file {file_path}")
                return

        pdfmetrics.registerFont(TTFont("Noto", "NotoSansSC-Regular.ttf"))
        doc = SimpleDocTemplate(file_path,pagesize=letter,
                                rightMargin=2*cm,leftMargin=2*cm,
                                topMargin=2*cm,bottomMargin=2*cm)

        paragraphs = []
        titleStyle = getSampleStyleSheet()["Heading1"]
        dateStyle = getSampleStyleSheet()["Heading2"]
        textStyle = getSampleStyleSheet()["Normal"]
        dateStyle.fontName = "Noto"
        textStyle.fontName = "Noto"

        # Add title
        title = Paragraph(f"slack channel: {self.name}", titleStyle)
        paragraphs += [title]

        for file in self.files:
            date = file[:-5]
            if dates_filter and date not in dates_filter:
                continue
            msgs = self.parse_file(file)
            date_paragraph = Paragraph(date.replace("\n", "<br />"), dateStyle)
            msgs_paragraph = Paragraph(msgs.replace("\n", "<br />"), textStyle)

            paragraphs += [date_paragraph, msgs_paragraph]

        logger.debug(f"Saving to file {file_path}")
        doc.build(paragraphs)

class SlackDB:
    def __init__(self, path) -> None:
        self.root = path

        self.channels_json = self.path("channels.json")
        self.dms_json = self.path("dms.json")
        self.groups_json = self.path("groups.json")
        self.mpims_json = self.path("mpims.json")
        self.users_json = self.path("users.json")

        self.users = {}
        self.channels = {}
        self.dms = {}
        self.chats = {}

    def path(self, path) -> str:
        return os.path.join(self.root, path)

    def _open_users(self):
        with open(self.users_json) as f:
            data = json.load(f)
        for d in data:
            self.users[d["id"]] = User(d)

    def _open_channels(self):
        with open(self.channels_json) as f:
            data = json.load(f)
        for d in data:
            self.channels[d["id"]] = d["name"]

    def _open_dms(self):
        with open(self.dms_json) as f:
            data = json.load(f)
        for d in data:
            self.dms[d["id"]] = " -- ".join([self.user_name(m) for m in d["members"]])

    def _open_chat(self, c) -> Chat:
        chat_name = c
        # Parse dm chat name
        if c in self.dms:
            chat_name = self.dms[c]
        chat = Chat(self.path(c), chat_name, self)
        self.chats[c] = chat
        return chat

    def _open_chats(self):
        for c in os.listdir(self.root):
            if os.path.isdir(self.path(c)):
                self._open_chat(c)

    def user_name(self, id) -> str:
        if id == "USLACKBOT":
            return "slack bot"
        return self.users[id].name

    def channel_name(self, id) -> str:
        return self.channels[id]

    def open(self):
        logger.info(f"Opening {self.root}")
        self._open_users()
        self._open_channels()
        self._open_dms()
        self._open_chats()

    def export(self, out_dir: str, force_rebuild: bool = False, filter = None):
        if not filter:
            for chat in self.chats.values():
                chat.export(out_dir, force_rebuild)

        else:
            chats = filter.get_chats()
            for c, dates in chats.items():
                self.chats[c].export(out_dir, force_rebuild, dates)

def parse_args():
    parser = argparse.ArgumentParser(description='Process input and output paths.')
    parser.add_argument('input_path', type=str, help='Path to the input file or directory')
    parser.add_argument('output_path', type=str, nargs='?', default='./out', help='Path to the output directory (default: ./out)')
    parser.add_argument('--log_level', type=str, choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], default='INFO', help='Set the logging level (default: INFO)')
    parser.add_argument('-f', action='store_true', help='Force rebuild')
    parser.add_argument('--filter', type=str, default='', help='Path to filter file, optional')

    return parser.parse_args()

def main():
    args = parse_args()

    logger.setLevel(getattr(logging, args.log_level))
    input_path = args.input_path
    output_path = args.output_path
    force_rebuild = args.f
    filter_file = args.filter

    filter = Filter(filter_file)

    if not os.path.exists(output_path):
        os.makedirs(output_path)

    db = SlackDB(input_path)
    db.open()
    db.export(output_path, force_rebuild, filter)

if __name__ == '__main__':
    main()
