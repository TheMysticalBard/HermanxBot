from typing import List, Literal, Optional

BlockType = Literal['rich_text', 'rich_text_section']
RichTextType = Literal['text', 'channel', 'user', 'emoji', 'link', 'team', 'usergroup', 'date', 'broadcast']

class Block:
    def __init__(self, my_dict: dict):
        for key in my_dict:
            setattr(self, key, my_dict[key])
    type: BlockType

class RichTextStyle:
    bold: Optional[bool]
    italic: Optional[bool]
    strike: Optional[bool]
    code: Optional[bool]

class RichTextElement:
    def __init__(self, my_dict: dict):
        self.style = None
        for key in my_dict:
            setattr(self, key, my_dict[key])
    type: RichTextType
    style: Optional[RichTextStyle]

class RichTextText(RichTextElement):
    text: str

class RichTextChannel(RichTextElement):
    channel_id: str

class RichTextUser(RichTextElement):
    user_id: str

class RichTextEmoji(RichTextElement):
    def __init__(self, my_dict: dict):
        super().__init__(my_dict)
        self.unicode = None
    name: str
    unicode: Optional[str]

class RichTextLink(RichTextElement):
    def __init__(self, my_dict: dict):
        super().__init__(my_dict)
        self.text = None
    url: str
    text: Optional[str]

class RichTextTeam(RichTextElement):
    team_id: str

class RichTextUsergroup(RichTextElement):
    usergroup_id: str

class RichTextDate(RichTextElement):
    timestamp: float

class RichTextBroadcast(RichTextElement):
    range: Literal["everyone", "here", "channel"]

class RichTextSection(Block):
    elements: List[RichTextElement]

class RichTextBlock(Block):
    elements: List[RichTextSection]