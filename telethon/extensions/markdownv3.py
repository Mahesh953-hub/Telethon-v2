import html
import re
from . import utils, html as htmlparser
from ..tl import types

# Delimiters
BOLD_DELIM = "**"
ITALIC_DELIM = "__"
UNDERLINE_DELIM = "--"
STRIKE_DELIM = "~~"
SPOILER_DELIM = "||"
CODE_DELIM = "`"
PRE_DELIM = "```"
BLOCKQUOTE_DELIM = ">"
BLOCKQUOTE_EXPANDABLE_DELIM = "**>"

# Regex for MarkdownV2 patterns
MARKDOWN_RE = re.compile(
    r"({d})|\[(.+?)\]\((.+?)\)".format(
        d="|".join(
            [
                "".join([rf"\{j}" for j in i])
                for i in [
                    PRE_DELIM,
                    CODE_DELIM,
                    STRIKE_DELIM,
                    UNDERLINE_DELIM,
                    ITALIC_DELIM,
                    BOLD_DELIM,
                    SPOILER_DELIM,
                ]
            ]
        )
    )
)

CODE_TAG_RE = re.compile(r"<code>.*?</code>")
OPENING_TAG = "<{}>"
CLOSING_TAG = "</{}>"
URL_MARKUP = '<a href="{}">{}</a>'


class MarkdownV3:
    def __init__(self):
        self.html = htmlparser

    @staticmethod
    def blockquote_parser(text: str) -> str:
        """Processes blockquote delimiters into HTML tags."""
        text = re.sub(r"\n>", "\n>", re.sub(r"^>", ">", text))
        lines = text.split("\n")
        result = []
        in_blockquote = False

        for line in lines:
            if line.startswith(BLOCKQUOTE_DELIM):
                if not in_blockquote:
                    tag = (
                        "blockquote expandable"
                        if line.startswith(BLOCKQUOTE_EXPANDABLE_DELIM)
                        else "blockquote"
                    )
                    prefix = (
                        BLOCKQUOTE_EXPANDABLE_DELIM
                        if tag == "blockquote expandable"
                        else BLOCKQUOTE_DELIM
                    )
                    line = OPENING_TAG.format(tag) + line[len(prefix):].strip()
                    in_blockquote = True
                    result.append(line)
                else:
                    prefix = (
                        BLOCKQUOTE_EXPANDABLE_DELIM
                        if line.startswith(BLOCKQUOTE_EXPANDABLE_DELIM)
                        else BLOCKQUOTE_DELIM
                    )
                    result.append(line[len(prefix):].strip())
            else:
                if in_blockquote:
                    result[-1] += CLOSING_TAG.format("blockquote")
                    in_blockquote = False
                result.append(line)

        if in_blockquote:
            result[-1] += CLOSING_TAG.format("blockquote")

        return "\n".join(result)

    def parse(self, text: str):
        """Converts MarkdownV3 text into (clean_text, entities)."""
        if not text:
            return text, []

        # 1. Handle blockquotes
        text = self.blockquote_parser(text)

        delims = set()
        is_fixed_width = False
        placeholders = {}

        # 2. Protect existing code sections
        for i, code_section in enumerate(CODE_TAG_RE.findall(text)):
            placeholder = f"{{CODE_SECTION_{i}}}"
            placeholders[placeholder] = code_section
            text = text.replace(code_section, placeholder, 1)

        # 3. Parse delimiters and links
        for match in list(re.finditer(MARKDOWN_RE, text)):
            start, _ = match.span()
            delim, text_url, url = match.groups()
            full = match.group(0)

            if delim in [CODE_DELIM, PRE_DELIM]:
                is_fixed_width = not is_fixed_width

            if is_fixed_width and delim not in [CODE_DELIM, PRE_DELIM]:
                continue

            if text_url:
                text = utils.replace_once(
                    text,
                    full,
                    URL_MARKUP.format(url, text_url),
                    start,
                )
                continue

            tag_map = {
                BOLD_DELIM: "b",
                ITALIC_DELIM: "i",
                UNDERLINE_DELIM: "u",
                STRIKE_DELIM: "s",
                CODE_DELIM: "code",
                PRE_DELIM: "pre",
                SPOILER_DELIM: "spoiler",
            }

            if delim in tag_map:
                tag = tag_map[delim]
                if delim not in delims:
                    delims.add(delim)
                    if delim == PRE_DELIM:
                        line_content = text[start:].split("\n")[0]
                        lang = line_content[len(PRE_DELIM):]
                        replacement = f'<pre language="{lang}">'
                        text = utils.replace_once(
                            text, line_content, replacement, start
                        )
                        continue
                    tag_str = OPENING_TAG.format(tag)
                else:
                    delims.remove(delim)
                    tag_str = CLOSING_TAG.format(tag)

                text = utils.replace_once(text, delim, tag_str, start)

        # Restore code placeholders
        for placeholder, code_section in placeholders.items():
            text = text.replace(placeholder, code_section)

        # 4. Convert HTML to entities
        clean_text, entities = self.html.parse(text)

        # 5. Apply CustomMarkdown logic (spoilers and custom emojis)
        for i, e in enumerate(entities):
            if isinstance(e, types.MessageEntityTextUrl):
                if e.url == "spoiler":
                    entities[i] = types.MessageEntitySpoiler(
                        e.offset, e.length
                    )
                elif e.url.startswith("emoji/"):
                    try:
                        eid = int(e.url.split("/")[1])
                        entities[i] = types.MessageEntityCustomEmoji(
                            e.offset, e.length, eid
                        )
                    except (IndexError, ValueError):
                        continue

        return clean_text, entities

    def unparse(self, text: str, entities: list):
        """Converts (text, entities) back into MarkdownV3 string."""
        if not text:
            return text

        text = utils.add_surrogates(text)
        entities_offsets = []

        for entity in (entities or []):
            start = entity.offset
            end = start + entity.length

            if isinstance(entity, types.MessageEntityCustomEmoji):
                start_tag, end_tag = "[", f"](emoji/{entity.document_id})"
            elif isinstance(entity, types.MessageEntitySpoiler):
                start_tag = end_tag = SPOILER_DELIM
            elif isinstance(entity, types.MessageEntityBold):
                start_tag = end_tag = BOLD_DELIM
            elif isinstance(entity, types.MessageEntityItalic):
                start_tag = end_tag = ITALIC_DELIM
            elif isinstance(entity, types.MessageEntityUnderline):
                start_tag = end_tag = UNDERLINE_DELIM
            elif isinstance(entity, types.MessageEntityStrike):
                start_tag = end_tag = STRIKE_DELIM
            elif isinstance(entity, types.MessageEntityCode):
                start_tag = end_tag = CODE_DELIM
            elif isinstance(entity, types.MessageEntityPre):
                lang = getattr(entity, "language", "") or ""
                start_tag = f"{PRE_DELIM}{lang}\n"
                end_tag = f"\n{PRE_DELIM}"
            elif isinstance(entity, types.MessageEntityTextUrl):
                start_tag, end_tag = "[", f"]({entity.url})"
            elif isinstance(entity, types.MessageEntityMentionName):
                start_tag, end_tag = "[", f"](tg://user?id={entity.user_id})"
            elif isinstance(entity, types.MessageEntityBlockquote):
                start_tag = (
                    BLOCKQUOTE_EXPANDABLE_DELIM + " "
                    if getattr(entity, "collapsed", False)
                    else BLOCKQUOTE_DELIM + " "
                )
                entities_offsets.append((start_tag, start))
                continue
            else:
                continue

            entities_offsets.append((start_tag, start))
            entities_offsets.append((end_tag, end))

        entities_offsets.sort(key=lambda x: x[1], reverse=True)

        for tag, offset in entities_offsets:
            text = text[:offset] + tag + text[offset:]

        return utils.remove_surrogates(text)
