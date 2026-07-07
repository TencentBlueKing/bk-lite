import re
from dataclasses import dataclass

from apps.monitor.expression.ast import BinaryOpNode, ExpressionNode, NumberNode, VariableNode
from apps.monitor.expression.errors import FormulaSyntaxError


TOKEN_RE = re.compile(
    r"""
    (?P<SPACE>\s+)
    |(?P<NUMBER>\d+(?:\.\d+)?)
    |(?P<IDENT>[a-zA-Z][a-zA-Z0-9_]*)
    |(?P<OP>[+\-*/()])
    |(?P<MISMATCH>.)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class Token:
    type: str
    value: str


def tokenize(expression: str) -> list[Token]:
    tokens: list[Token] = []
    for match in TOKEN_RE.finditer(expression or ""):
        kind = match.lastgroup or "MISMATCH"
        value = match.group()
        if kind == "SPACE":
            continue
        if kind == "MISMATCH":
            raise FormulaSyntaxError(f"表达式包含非法字符：{value}")
        if kind == "OP":
            tokens.append(Token(value, value))
            continue
        tokens.append(Token(kind, value))
    return tokens


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.position = 0

    def parse(self) -> ExpressionNode:
        if not self.tokens:
            raise FormulaSyntaxError("表达式不能为空")

        node = self.parse_additive()
        if self.current is not None:
            if self.current.value == ")":
                raise FormulaSyntaxError("括号不匹配：多余右括号")
            raise FormulaSyntaxError(f"表达式存在多余内容：{self.current.value}")
        return node

    @property
    def current(self) -> Token | None:
        if self.position >= len(self.tokens):
            return None
        return self.tokens[self.position]

    def advance(self) -> Token:
        token = self.current
        if token is None:
            raise FormulaSyntaxError("表达式不完整")
        self.position += 1
        return token

    def match(self, *values: str) -> Token | None:
        token = self.current
        if token is None or token.value not in values:
            return None
        self.position += 1
        return token

    def parse_additive(self) -> ExpressionNode:
        node = self.parse_multiplicative()
        while self.current is not None and self.current.value in {"+", "-"}:
            operator = self.advance().value
            right = self.parse_multiplicative()
            node = BinaryOpNode(operator=operator, left=node, right=right)
        return node

    def parse_multiplicative(self) -> ExpressionNode:
        node = self.parse_primary()
        while self.current is not None and self.current.value in {"*", "/"}:
            operator = self.advance().value
            right = self.parse_primary()
            node = BinaryOpNode(operator=operator, left=node, right=right)
        return node

    def parse_primary(self) -> ExpressionNode:
        token = self.advance()
        if token.type == "NUMBER":
            return NumberNode(value=self.parse_number(token.value))
        if token.type == "IDENT":
            return VariableNode(name=token.value)
        if token.value == "(":
            node = self.parse_additive()
            if self.match(")") is None:
                raise FormulaSyntaxError("括号不匹配：缺少右括号")
            return node
        if token.value == ")":
            raise FormulaSyntaxError("括号不匹配：多余右括号")
        raise FormulaSyntaxError(f"表达式不完整：{token.value}")

    @staticmethod
    def parse_number(value: str) -> float | int:
        if "." in value:
            return float(value)
        return int(value)


def parse_expression(expression: str) -> ExpressionNode:
    return Parser(tokenize(expression)).parse()
