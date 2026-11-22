from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.errors import RegisterError

Code = Annotated[str, Field(pattern=r'^[A-Z0-9][A-Z0-9-]{0,23}$')]
Side = Literal['N', 'E', 'S', 'W']
OPPOSITE = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}


class Sheet(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: Code
    title: Annotated[str, Field(min_length=1, max_length=30)]
    width_px: Annotated[int, Field(ge=100, le=100_000)]
    height_px: Annotated[int, Field(ge=100, le=100_000)]


class Edge(BaseModel):
    model_config = ConfigDict(extra='forbid')
    code: Code
    a: Code
    b: Code
    a_side: Side
    b_side: Side
    reverse: bool = False


class Catalog(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    title: Annotated[str, Field(min_length=1, max_length=40)]
    version: Annotated[str, Field(min_length=1, max_length=25)]
    longitude_deg: Annotated[float, Field(ge=-180, le=180)]
    latitude_deg: Annotated[float, Field(gt=-90, lt=90)]
    sheets: Annotated[list[Sheet], Field(min_length=1, max_length=24)]
    edges: Annotated[list[Edge], Field(max_length=48)]
    aliases: Annotated[dict[str, str], Field(max_length=256)]

    @model_validator(mode='after')
    def check_references(self):
        sheets = {sheet.code for sheet in self.sheets}
        if len(sheets) != len(self.sheets) or len({edge.code for edge in self.edges}) != len(self.edges):
            raise ValueError('图幅编号或拼缝编号重复')
        sides = set()
        for edge in self.edges:
            if edge.a == edge.b or not {edge.a, edge.b} <= sheets or OPPOSITE[edge.a_side] != edge.b_side:
                raise ValueError(f'{edge.code} 的图幅或边向无效')
            endpoints = {(edge.a, edge.a_side), (edge.b, edge.b_side)}
            if endpoints & sides:
                raise ValueError(f'{edge.code} 重复登记图边')
            sides.update(endpoints)
        return self


def read_catalog(raw):
    try:
        return Catalog.model_validate_json(raw)
    except ValidationError as error:
        issues = [{'field': '.'.join(map(str, issue['loc'])), 'message': issue['msg']}
                  for issue in error.errors(include_input=False)]
        raise RegisterError('BAD_CATALOG', '图幅登记册无效', evidence=issues) from error
