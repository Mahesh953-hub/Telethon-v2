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


class MarkdownV3:
    def __init__(self):
        self.html = htmlparser

    @staticmethod
    def blockquote_parser(text: str) -> str:
        if not text:
            return ""

        lines = text.split("\n")
        result = []
        in_blockquote = False
        is_expandable = False

        for line in lines:
            if (
                line.startswith(BLOCKQUOTE_EXPANDABLE_DELIM)
                or line.startswith(BLOCKQUOTE_DELIM)
            ):
                current_expandable = line.startswith(BLOCKQUOTE_EXPANDABLE_DELIM)
                prefix = (
                    BLOCKQUOTE_EXPANDABLE_DELIM
                    if current_expandable
                    else BLOCKQUOTE_DELIM
                )
                content = line[len(prefix):].lstrip()

                if not in_blockquote:
                    tag = (
                        "blockquote expandable"
                        if current_expandable
                        else "blockquote"
                    )
                    result.append(f"<{tag}>{content}")
                    in_blockquote = True
                    is_expandable = current_expandable
                else:
                    result.append(content)
            else:
                if in_blockquote:
                    result[-1] += "</blockquote>"
                    in_blockquote = False
                result.append(line)

        if in_blockquote and result:
            result[-1] += "</blockquote>"

        return "\n".join(result)

    def parse(self, text: str):
        if not text:
            return "", []

        # 1. Handle blockquotes
        text = self.blockquote_parser(text)

        # 2. Protect existing code sections
        placeholders = {}
        code_matches = list(CODE_TAG_RE.finditer(text))
        for i, m in enumerate(reversed(code_matches)):
            placeholder = f"{{CODE_SECTION_{i}}}"
            placeholders[placeholder] = m.group(0)
            text = text[:m.start()] + placeholder + text[m.end():]

        # 3. Parse delimiters (reverse order to keep offsets valid)
        delims = {}
        matches = list(MARKDOWN_RE.finditer(text))

        for match in reversed(matches):
            start, end = match.span()
            delim, text_url, url = match.groups()

            if text_url:
                replacement = f'<a href="{url}">{text_url}</a>'
                text = text[:start] + replacement + text[end:]
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

            if delim not in tag_map:
                continue

            tag = tag_map[delim]
            count = delims.get(delim, 0)

            if count % 2 == 0:
                tag_str = f"</{tag}>"
            else:
                if delim == PRE_DELIM:
                    line_part = text[end:].split("\n")[0]
                    tag_str = f'<pre language="{line_part}">'
                    text = text[:end] + text[end + len(line_part):]
                else:
                    tag_str = f"<{tag}>"

            delims[delim] = count + 1
            text = text[:start] + tag_str + text[end:]

        # Restore code placeholders
        for placeholder, code_section in placeholders.items():
            text = text.replace(placeholder, code_section)

        # 4. Convert HTML to entities
        clean_text, entities = self.html.parse(text)

        # 5. Post-process custom emojis and spoilers
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
        if not text:
            return ""

        text = utils.add_surrogates(text)
        insertions = []

        for entity in (entities or []):
            start = entity.offset
            end = start + entity.length

            if isinstance(entity, types.MessageEntityCustomEmoji):
                insertions.append((start, "["))
                insertions.append((end, f"](emoji/{entity.document_id})"))
            elif isinstance(entity, types.MessageEntitySpoiler):
                insertions.append((start, SPOILER_DELIM))
                insertions.append((end, SPOILER_DELIM))
            elif isinstance(entity, types.MessageEntityBold):
                insertions.append((start, BOLD_DELIM))
                insertions.append((end, BOLD_DELIM))
            elif isinstance(entity, types.MessageEntityItalic):
                insertions.append((start, ITALIC_DELIM))
                insertions.append((end, ITALIC_DELIM))
            elif isinstance(entity, types.MessageEntityUnderline):
                insertions.append((start, UNDERLINE_DELIM))
                insertions.append((end, UNDERLINE_DELIM))
            elif isinstance(entity, types.MessageEntityStrike):
                insertions.append((start, STRIKE_DELIM))
                insertions.append((end, STRIKE_DELIM))
            elif isinstance(entity, types.MessageEntityCode):
                insertions.append((start, CODE_DELIM))
                insertions.append((end, CODE_DELIM))
            elif isinstance(entity, types.MessageEntityPre):
                lang = getattr(entity, "language", "") or ""
                insertions.append((start, f"{PRE_DELIM}{lang}\n"))
                insertions.append((end, f"\n{PRE_DELIM}"))
            elif isinstance(entity, types.MessageEntityTextUrl):
                insertions.append((start, "["))
                insertions.append((end, f"]({entity.url})"))
            elif isinstance(entity, types.MessageEntityMentionName):
                insertions.append((start, "["))
                insertions.append(
                    (end, f"](tg://user?id={entity.user_id})")
                )
            elif isinstance(entity, types.MessageEntityBlockquote):
                prefix = (
                    BLOCKQUOTE_EXPANDABLE_DELIM
                    if getattr(entity, "collapsed", False)
                    else BLOCKQUOTE_DELIM
                )
                insertions.append((start, f"{prefix} "))

        insertions.sort(key=lambda x: x[0], reverse=True)

        for offset, tag in insertions:
            text = text[:offset] + tag + text[offset:]

        return utils.remove_surrogates(text)
