package rumreplayreceiver

import (
	"io"
	"regexp"
	"strconv"
	"strings"
	"unicode/utf8"

	parse "github.com/tdewolff/parse/v2"
	"github.com/tdewolff/parse/v2/css"
)

const (
	maxInlineCSSBytes     = 64 * 1024
	maxStylesheetCSSBytes = 1024 * 1024
	maxCSSValueBytes      = 16 * 1024
	maxCSSGrammarItems    = 100_000
	maxCSSTokens          = 250_000
)

type cssTokenContext uint8

const (
	cssValueTokens cssTokenContext = iota
	cssSelectorTokens
	cssAtRulePreludeTokens
)

type cssBlockKind uint8

const (
	cssRulesetBlock cssBlockKind = iota
	cssAtRuleBlock
)

type cssBlockState struct {
	kind cssBlockKind
	emit bool
}

type cssSanitizeResult struct {
	css           string
	topLevelRules int
	ok            bool
}

var safeCSSAtRules = map[string]struct{}{
	"keyframes":         {},
	"-webkit-keyframes": {},
	"layer":             {},
	"media":             {},
	"supports":          {},
}

var cssRequestSyntaxPattern = regexp.MustCompile(`(?i)(?:^|[;{])\s*@(import|font-face)\b|(?:url|image-set|cross-fade|element|paint)\s*\(`)

func containsCSSRequestSyntax(raw string) bool {
	decoded, ok := decodeCSSEscapes(raw)
	return !ok || cssRequestSyntaxPattern.MatchString(decoded)
}

var safeCSSProperties = map[string]struct{}{
	"accent-color": {}, "align-content": {}, "align-items": {}, "align-self": {},
	"alignment-baseline": {}, "animation": {}, "animation-delay": {}, "animation-direction": {},
	"animation-duration": {}, "animation-fill-mode": {}, "animation-iteration-count": {},
	"animation-name": {}, "animation-play-state": {}, "animation-timing-function": {},
	"appearance": {}, "aspect-ratio": {}, "backface-visibility": {}, "backdrop-filter": {},
	"background": {}, "background-attachment": {}, "background-clip": {}, "background-color": {},
	"background-image": {}, "background-origin": {}, "background-position": {},
	"background-position-x": {}, "background-position-y": {}, "background-repeat": {},
	"background-size": {}, "border": {}, "border-block": {}, "border-block-color": {},
	"border-block-end": {}, "border-block-end-color": {}, "border-block-end-style": {},
	"border-block-end-width": {}, "border-block-start": {}, "border-block-start-color": {},
	"border-block-start-style": {}, "border-block-start-width": {}, "border-block-style": {},
	"border-block-width": {}, "border-bottom": {}, "border-bottom-color": {},
	"border-bottom-left-radius": {}, "border-bottom-right-radius": {}, "border-bottom-style": {},
	"border-bottom-width": {}, "border-collapse": {}, "border-color": {}, "border-end-end-radius": {},
	"border-end-start-radius": {}, "border-inline": {}, "border-inline-color": {},
	"border-inline-end": {}, "border-inline-end-color": {}, "border-inline-end-style": {},
	"border-inline-end-width": {}, "border-inline-start": {}, "border-inline-start-color": {},
	"border-inline-start-style": {}, "border-inline-start-width": {}, "border-inline-style": {},
	"border-inline-width": {}, "border-left": {}, "border-left-color": {}, "border-left-style": {},
	"border-left-width": {}, "border-radius": {}, "border-right": {}, "border-right-color": {},
	"border-right-style": {}, "border-right-width": {}, "border-spacing": {}, "border-start-end-radius": {},
	"border-start-start-radius": {}, "border-style": {}, "border-top": {}, "border-top-color": {},
	"border-top-left-radius": {}, "border-top-right-radius": {}, "border-top-style": {},
	"border-top-width": {}, "border-width": {}, "bottom": {}, "box-shadow": {}, "box-sizing": {},
	"caption-side": {}, "caret-color": {}, "clear": {}, "clip-path": {}, "color": {},
	"color-scheme": {}, "column-count": {}, "column-fill": {}, "column-gap": {}, "column-rule": {},
	"column-rule-color": {}, "column-rule-style": {}, "column-rule-width": {}, "column-span": {},
	"column-width": {}, "columns": {}, "content-visibility": {}, "cursor": {}, "direction": {},
	"display": {}, "dominant-baseline": {}, "empty-cells": {}, "fill": {}, "fill-opacity": {},
	"fill-rule": {}, "filter": {}, "flex": {}, "flex-basis": {}, "flex-direction": {},
	"flex-flow": {}, "flex-grow": {}, "flex-shrink": {}, "flex-wrap": {}, "float": {},
	"flood-color": {}, "flood-opacity": {}, "font": {}, "font-family": {},
	"font-feature-settings": {}, "font-kerning": {}, "font-optical-sizing": {}, "font-size": {},
	"font-size-adjust": {}, "font-stretch": {}, "font-style": {}, "font-variant": {},
	"font-variant-caps": {}, "font-weight": {}, "gap": {}, "grid": {}, "grid-area": {},
	"grid-auto-columns": {}, "grid-auto-flow": {}, "grid-auto-rows": {}, "grid-column": {},
	"grid-column-end": {}, "grid-column-start": {}, "grid-row": {}, "grid-row-end": {},
	"grid-row-start": {}, "grid-template": {}, "grid-template-areas": {}, "grid-template-columns": {},
	"grid-template-rows": {}, "height": {}, "hyphens": {}, "inset": {}, "inset-block": {},
	"inset-block-end": {}, "inset-block-start": {}, "inset-inline": {}, "inset-inline-end": {},
	"inset-inline-start": {}, "isolation": {}, "justify-content": {}, "justify-items": {},
	"justify-self": {}, "left": {}, "letter-spacing": {}, "lighting-color": {}, "line-height": {},
	"list-style": {}, "list-style-position": {}, "list-style-type": {}, "margin": {}, "margin-block": {},
	"margin-block-end": {}, "margin-block-start": {}, "margin-bottom": {}, "margin-inline": {},
	"margin-inline-end": {}, "margin-inline-start": {}, "margin-left": {}, "margin-right": {},
	"margin-top": {}, "max-block-size": {}, "max-height": {}, "max-inline-size": {},
	"max-width": {}, "min-block-size": {}, "min-height": {}, "min-inline-size": {}, "min-width": {},
	"object-fit": {}, "object-position": {}, "opacity": {}, "order": {}, "outline": {},
	"outline-color": {}, "outline-offset": {}, "outline-style": {}, "outline-width": {},
	"overflow": {}, "overflow-anchor": {}, "overflow-block": {}, "overflow-inline": {},
	"overflow-wrap": {}, "overflow-x": {}, "overflow-y": {}, "padding": {}, "padding-block": {},
	"padding-block-end": {}, "padding-block-start": {}, "padding-bottom": {}, "padding-inline": {},
	"padding-inline-end": {}, "padding-inline-start": {}, "padding-left": {}, "padding-right": {},
	"padding-top": {}, "paint-order": {}, "perspective": {}, "perspective-origin": {},
	"place-content": {}, "place-items": {}, "place-self": {}, "pointer-events": {}, "position": {},
	"right": {}, "rotate": {}, "row-gap": {}, "scale": {}, "shape-rendering": {}, "stop-color": {},
	"stop-opacity": {}, "stroke": {}, "stroke-dasharray": {}, "stroke-dashoffset": {},
	"stroke-linecap": {}, "stroke-linejoin": {}, "stroke-miterlimit": {}, "stroke-opacity": {},
	"stroke-width": {}, "tab-size": {}, "table-layout": {}, "text-align": {}, "text-align-last": {},
	"text-anchor": {}, "text-decoration": {}, "text-decoration-color": {}, "text-decoration-line": {},
	"text-decoration-style": {}, "text-decoration-thickness": {}, "text-indent": {},
	"text-overflow": {}, "text-shadow": {}, "text-size-adjust": {}, "text-transform": {},
	"text-underline-offset": {}, "top": {}, "transform": {}, "transform-box": {},
	"transform-origin": {}, "transform-style": {}, "transition": {}, "transition-delay": {},
	"transition-duration": {}, "transition-property": {}, "transition-timing-function": {},
	"translate": {}, "unicode-bidi": {}, "user-select": {}, "vector-effect": {},
	"vertical-align": {}, "visibility": {}, "white-space": {}, "width": {}, "will-change": {},
	"word-break": {}, "word-spacing": {}, "word-wrap": {}, "writing-mode": {}, "z-index": {},
	"-moz-osx-font-smoothing": {}, "-webkit-appearance": {}, "-webkit-box-orient": {},
	"-webkit-font-smoothing": {}, "-webkit-line-clamp": {}, "-webkit-text-size-adjust": {},
	"-webkit-transform": {}, "-webkit-transform-origin": {}, "-webkit-user-select": {},
}

var safeCSSFunctions = map[string]struct{}{
	"blur": {}, "brightness": {}, "calc": {}, "circle": {}, "clamp": {}, "color": {},
	"color-mix": {}, "conic-gradient": {}, "contrast": {}, "cubic-bezier": {},
	"drop-shadow": {}, "ellipse": {}, "env": {}, "fit-content": {}, "grayscale": {},
	"hsl": {}, "hsla": {}, "hue-rotate": {}, "hwb": {}, "inset": {}, "invert": {},
	"lab": {}, "lch": {}, "linear-gradient": {}, "matrix": {}, "matrix3d": {}, "max": {},
	"min": {}, "minmax": {}, "oklab": {}, "oklch": {}, "opacity": {}, "perspective": {},
	"polygon": {}, "radial-gradient": {}, "repeat": {}, "repeating-conic-gradient": {},
	"repeating-linear-gradient": {}, "repeating-radial-gradient": {}, "rgb": {}, "rgba": {},
	"rotate": {}, "rotate3d": {}, "rotatex": {}, "rotatey": {}, "rotatez": {}, "saturate": {},
	"scale": {}, "scale3d": {}, "scalex": {}, "scaley": {}, "scalez": {}, "sepia": {},
	"skew": {}, "skewx": {}, "skewy": {}, "steps": {}, "translate": {}, "translate3d": {},
	"translatex": {}, "translatey": {}, "translatez": {}, "var": {},
}

var forbiddenCSSFunctions = map[string]struct{}{
	"cross-fade": {}, "element": {}, "expression": {}, "image": {}, "image-set": {},
	"paint": {}, "url": {}, "-webkit-image-set": {},
}

func sanitizeInlineCSS(input string) string {
	result := sanitizeCSS(input, true, maxInlineCSSBytes)
	if !result.ok {
		return ""
	}
	return result.css
}

func sanitizeStylesheetCSS(input string) string {
	result := sanitizeCSS(input, false, maxStylesheetCSSBytes)
	if !result.ok {
		return ""
	}
	return result.css
}

func sanitizeSingleCSSRule(input string) (string, bool) {
	result := sanitizeCSS(input, false, maxStylesheetCSSBytes)
	if !result.ok || result.topLevelRules != 1 || result.css == "" {
		return "", false
	}
	return result.css, true
}

func sanitizeCSSDeclaration(property string, value string, priority string) (string, string, string, bool) {
	property, ok := normalizeReplayCSSProperty(property)
	if !ok || len(value) > maxCSSValueBytes {
		return "", "", "", false
	}
	priority = strings.ToLower(strings.TrimSpace(priority))
	if priority != "" && priority != "important" {
		return "", "", "", false
	}
	declaration := property + ":" + value
	if priority == "important" {
		declaration += "!important"
	}
	result := sanitizeCSS(declaration, true, maxInlineCSSBytes)
	if !result.ok || result.css == "" {
		return "", "", "", false
	}
	prefix := property + ":"
	if !strings.HasPrefix(result.css, prefix) || !strings.HasSuffix(result.css, ";") {
		return "", "", "", false
	}
	normalized := strings.TrimSuffix(strings.TrimPrefix(result.css, prefix), ";")
	if priority == "important" {
		if !strings.HasSuffix(normalized, "!important") {
			return "", "", "", false
		}
		normalized = strings.TrimSuffix(normalized, "!important")
	}
	if normalized == "" {
		return "", "", "", false
	}
	return property, normalized, priority, true
}

func normalizeReplayCSSProperty(raw string) (string, bool) {
	if strings.HasPrefix(raw, "--") || strings.HasPrefix(raw, "\\") {
		if property, ok := normalizeCSSCustomProperty(raw); ok {
			return property, true
		}
	}
	return normalizeSafeCSSProperty(raw)
}

func sanitizeCSS(input string, inline bool, maxBytes int) cssSanitizeResult {
	if input == "" {
		return cssSanitizeResult{ok: true}
	}
	if len(input) > maxBytes || !validCSSInput(input) {
		return cssSanitizeResult{}
	}

	parser := css.NewParser(parse.NewInputString(input), inline)
	var output strings.Builder
	output.Grow(min(len(input), maxBytes))
	blocks := make([]cssBlockState, 0, 8)
	pendingSelector := make([]css.Token, 0, 8)
	topLevelRules := 0
	grammarItems := 0
	tokenCount := 0

	for {
		grammar, tokenType, data := parser.Next()
		grammarItems++
		if grammarItems > maxCSSGrammarItems {
			return cssSanitizeResult{}
		}
		if grammar == css.ErrorGrammar {
			if parser.HasParseError() || parser.Err() != io.EOF {
				return cssSanitizeResult{}
			}
			break
		}

		values := parser.Values()
		tokenCount += 1 + len(values)
		if tokenCount > maxCSSTokens {
			return cssSanitizeResult{}
		}
		parentEmits := len(blocks) == 0 || blocks[len(blocks)-1].emit

		switch grammar {
		case css.CommentGrammar:
			// Comments are not needed for replay fidelity.
		case css.AtRuleGrammar:
			if len(blocks) == 0 {
				topLevelRules++
			}
			pendingSelector = pendingSelector[:0]
			if !parentEmits {
				continue
			}
			name, ok := decodeCSSAtRuleName(data)
			if !ok || name != "layer" {
				continue
			}
			prelude, ok := sanitizeCSSTokenSequence(values, cssAtRulePreludeTokens)
			if !ok {
				continue
			}
			output.WriteString("@layer")
			writeCSSAtRulePrelude(&output, prelude)
			output.WriteByte(';')
		case css.BeginAtRuleGrammar:
			if len(blocks) == 0 {
				topLevelRules++
			}
			pendingSelector = pendingSelector[:0]
			name, nameOK := decodeCSSAtRuleName(data)
			_, allowedAtRule := safeCSSAtRules[name]
			prelude, preludeOK := sanitizeCSSTokenSequence(values, cssAtRulePreludeTokens)
			emit := parentEmits && nameOK && allowedAtRule && preludeOK
			blocks = append(blocks, cssBlockState{kind: cssAtRuleBlock, emit: emit})
			if emit {
				output.WriteByte('@')
				output.WriteString(name)
				writeCSSAtRulePrelude(&output, prelude)
				output.WriteByte('{')
			}
		case css.EndAtRuleGrammar:
			if len(blocks) == 0 || blocks[len(blocks)-1].kind != cssAtRuleBlock {
				return cssSanitizeResult{}
			}
			block := blocks[len(blocks)-1]
			blocks = blocks[:len(blocks)-1]
			if block.emit {
				output.WriteByte('}')
			}
		case css.QualifiedRuleGrammar:
			pendingSelector = append(pendingSelector, css.Token{TokenType: tokenType, Data: append([]byte(nil), data...)})
			pendingSelector = appendCopiedCSSTokens(pendingSelector, values)
			pendingSelector = append(pendingSelector, css.Token{TokenType: css.CommaToken, Data: []byte(",")})
		case css.BeginRulesetGrammar:
			if len(blocks) == 0 {
				topLevelRules++
			}
			pendingSelector = append(pendingSelector, css.Token{TokenType: tokenType, Data: append([]byte(nil), data...)})
			pendingSelector = appendCopiedCSSTokens(pendingSelector, values)
			selector, selectorOK := sanitizeCSSTokenSequence(pendingSelector, cssSelectorTokens)
			pendingSelector = pendingSelector[:0]
			emit := parentEmits && selectorOK && selector != ""
			blocks = append(blocks, cssBlockState{kind: cssRulesetBlock, emit: emit})
			if emit {
				output.WriteString(selector)
				output.WriteByte('{')
			}
		case css.EndRulesetGrammar:
			if len(blocks) == 0 || blocks[len(blocks)-1].kind != cssRulesetBlock {
				return cssSanitizeResult{}
			}
			block := blocks[len(blocks)-1]
			blocks = blocks[:len(blocks)-1]
			if block.emit {
				output.WriteByte('}')
			}
		case css.DeclarationGrammar:
			if !parentEmits {
				continue
			}
			property, ok := normalizeSafeCSSProperty(string(data))
			if !ok {
				continue
			}
			value, ok := sanitizeCSSValueTokens(values)
			if !ok || value == "" || len(value) > maxCSSValueBytes {
				continue
			}
			output.WriteString(property)
			output.WriteByte(':')
			output.WriteString(value)
			output.WriteByte(';')
		case css.CustomPropertyGrammar:
			if !parentEmits {
				continue
			}
			property, ok := normalizeCSSCustomProperty(string(data))
			if !ok || len(values) != 1 || values[0].TokenType != css.CustomPropertyValueToken {
				continue
			}
			value, ok := sanitizeRawCSSValue(string(values[0].Data))
			if !ok || value == "" || len(value) > maxCSSValueBytes {
				continue
			}
			output.WriteString(property)
			output.WriteByte(':')
			output.WriteString(value)
			output.WriteByte(';')
		case css.TokenGrammar:
			if parentEmits && tokenType != css.CDOToken && tokenType != css.CDCToken {
				return cssSanitizeResult{}
			}
		default:
			return cssSanitizeResult{}
		}

		if output.Len() > maxBytes {
			return cssSanitizeResult{}
		}
	}

	if len(blocks) != 0 || len(pendingSelector) != 0 {
		return cssSanitizeResult{}
	}
	return cssSanitizeResult{css: output.String(), topLevelRules: topLevelRules, ok: true}
}

func sanitizeCSSValueTokens(tokens []css.Token) (string, bool) {
	return sanitizeCSSTokenSequence(tokens, cssValueTokens)
}

func sanitizeRawCSSValue(value string) (string, bool) {
	if len(value) > maxCSSValueBytes || !validCSSInput(value) {
		return "", false
	}
	lexer := css.NewLexer(parse.NewInputString(value))
	tokens := make([]css.Token, 0, 16)
	for len(tokens) <= maxCSSTokens {
		tokenType, data := lexer.Next()
		if tokenType == css.ErrorToken {
			if lexer.Err() != io.EOF {
				return "", false
			}
			break
		}
		tokens = append(tokens, css.Token{TokenType: tokenType, Data: append([]byte(nil), data...)})
	}
	if len(tokens) > maxCSSTokens {
		return "", false
	}
	return sanitizeCSSTokenSequence(tokens, cssValueTokens)
}

func sanitizeCSSTokenSequence(tokens []css.Token, context cssTokenContext) (string, bool) {
	if len(tokens) == 0 {
		return "", true
	}
	var output strings.Builder
	stack := make([]css.TokenType, 0, 8)
	for _, token := range tokens {
		switch token.TokenType {
		case css.ErrorToken, css.BadStringToken, css.URLToken, css.BadURLToken, css.AtKeywordToken,
			css.SemicolonToken, css.LeftBraceToken, css.RightBraceToken, css.CDOToken, css.CDCToken,
			css.CustomPropertyValueToken:
			return "", false
		case css.CommentToken:
			writeCSSSpace(&output)
			continue
		case css.WhitespaceToken:
			writeCSSSpace(&output)
			continue
		case css.FunctionToken:
			name, ok := decodeCSSFunctionName(token.Data)
			if !ok || name == "url" {
				return "", false
			}
			if context == cssValueTokens {
				if _, ok := safeCSSFunctions[name]; !ok {
					return "", false
				}
			} else if _, forbidden := forbiddenCSSFunctions[name]; forbidden {
				return "", false
			}
			stack = append(stack, css.RightParenthesisToken)
		case css.LeftParenthesisToken:
			stack = append(stack, css.RightParenthesisToken)
		case css.LeftBracketToken:
			stack = append(stack, css.RightBracketToken)
		case css.RightParenthesisToken, css.RightBracketToken:
			if len(stack) == 0 || stack[len(stack)-1] != token.TokenType {
				return "", false
			}
			stack = stack[:len(stack)-1]
		}
		output.Write(token.Data)
		if output.Len() > maxCSSValueBytes && context == cssValueTokens {
			return "", false
		}
	}
	if len(stack) != 0 {
		return "", false
	}
	return strings.TrimSpace(output.String()), true
}

func writeCSSSpace(output *strings.Builder) {
	value := output.String()
	if value == "" || value[len(value)-1] == ' ' {
		return
	}
	output.WriteByte(' ')
}

// writeCSSAtRulePrelude 在 prelude 以标识符开头时补空格（如 @keyframes name），
// 以 '(' 开头则保持紧凑（如 @media(...)）。
func writeCSSAtRulePrelude(output *strings.Builder, prelude string) {
	if prelude == "" {
		return
	}
	if prelude[0] != '(' && prelude[0] != '[' && prelude[0] != ' ' {
		output.WriteByte(' ')
	}
	output.WriteString(prelude)
}

func appendCopiedCSSTokens(destination []css.Token, tokens []css.Token) []css.Token {
	for _, token := range tokens {
		destination = append(destination, css.Token{
			TokenType: token.TokenType,
			Data:      append([]byte(nil), token.Data...),
		})
	}
	return destination
}

func normalizeSafeCSSProperty(raw string) (string, bool) {
	decoded, ok := decodeCSSIdentifier(raw)
	if !ok {
		return "", false
	}
	property := strings.ToLower(decoded)
	_, ok = safeCSSProperties[property]
	return property, ok
}

func normalizeCSSCustomProperty(raw string) (string, bool) {
	decoded, ok := decodeCSSIdentifier(raw)
	if !ok || len(decoded) < 3 || len(decoded) > 128 || !strings.HasPrefix(decoded, "--") {
		return "", false
	}
	for _, r := range decoded[2:] {
		if !isCSSNameRune(r) {
			return "", false
		}
	}
	return decoded, true
}

func decodeCSSAtRuleName(raw []byte) (string, bool) {
	if len(raw) < 2 || raw[0] != '@' {
		return "", false
	}
	decoded, ok := decodeCSSIdentifier(string(raw[1:]))
	if !ok {
		return "", false
	}
	return strings.ToLower(decoded), true
}

func decodeCSSFunctionName(raw []byte) (string, bool) {
	if len(raw) < 2 || raw[len(raw)-1] != '(' {
		return "", false
	}
	decoded, ok := decodeCSSIdentifier(string(raw[:len(raw)-1]))
	if !ok {
		return "", false
	}
	return strings.ToLower(decoded), true
}

func decodeCSSIdentifier(raw string) (string, bool) {
	decoded, ok := decodeCSSEscapes(raw)
	if !ok {
		return "", false
	}
	for _, r := range decoded {
		if !isCSSNameRune(r) {
			return "", false
		}
	}
	return decoded, true
}

func decodeCSSEscapes(raw string) (string, bool) {
	if raw == "" || !utf8.ValidString(raw) {
		return "", false
	}
	var output strings.Builder
	for index := 0; index < len(raw); {
		if raw[index] != '\\' {
			r, size := utf8.DecodeRuneInString(raw[index:])
			if r == utf8.RuneError && size == 1 {
				return "", false
			}
			output.WriteRune(r)
			index += size
			continue
		}

		index++
		if index >= len(raw) || raw[index] == '\n' || raw[index] == '\r' || raw[index] == '\f' {
			return "", false
		}
		if isASCIIHex(raw[index]) {
			start := index
			for index < len(raw) && index-start < 6 && isASCIIHex(raw[index]) {
				index++
			}
			value, err := strconv.ParseUint(raw[start:index], 16, 32)
			if err != nil {
				return "", false
			}
			r := rune(value)
			if r == 0 || r > utf8.MaxRune || 0xD800 <= r && r <= 0xDFFF {
				r = utf8.RuneError
			}
			output.WriteRune(r)
			if index < len(raw) && isCSSWhitespaceByte(raw[index]) {
				if raw[index] == '\r' && index+1 < len(raw) && raw[index+1] == '\n' {
					index++
				}
				index++
			}
			continue
		}

		r, size := utf8.DecodeRuneInString(raw[index:])
		if r == utf8.RuneError && size == 1 {
			return "", false
		}
		output.WriteRune(r)
		index += size
	}
	decoded := output.String()
	if decoded == "" {
		return "", false
	}
	return decoded, true
}

func validCSSInput(value string) bool {
	if !utf8.ValidString(value) {
		return false
	}
	for _, r := range value {
		if r == 0 || r == '\u007f' || r < '\u0020' && r != '\t' && r != '\n' && r != '\r' && r != '\f' {
			return false
		}
	}
	return balancedCSSDelimiters(value)
}

func balancedCSSDelimiters(value string) bool {
	stack := make([]byte, 0, 16)
	var quote byte
	for index := 0; index < len(value); index++ {
		current := value[index]
		if quote != 0 {
			if current == '\\' {
				index++
				if index >= len(value) || value[index] == '\n' || value[index] == '\r' || value[index] == '\f' {
					return false
				}
				continue
			}
			if current == quote {
				quote = 0
			}
			continue
		}
		if current == '/' && index+1 < len(value) && value[index+1] == '*' {
			end := strings.Index(value[index+2:], "*/")
			if end < 0 {
				return false
			}
			index += end + 3
			continue
		}
		if current == '\\' {
			index++
			if index >= len(value) {
				return false
			}
			continue
		}
		switch current {
		case '\'', '"':
			quote = current
		case '{':
			stack = append(stack, '}')
		case '(':
			stack = append(stack, ')')
		case '[':
			stack = append(stack, ']')
		case '}', ')', ']':
			if len(stack) == 0 || stack[len(stack)-1] != current {
				return false
			}
			stack = stack[:len(stack)-1]
		}
	}
	return quote == 0 && len(stack) == 0
}

func isCSSNameRune(r rune) bool {
	return r == '-' || r == '_' || '0' <= r && r <= '9' || 'a' <= r && r <= 'z' ||
		'A' <= r && r <= 'Z' || r >= utf8.RuneSelf
}

func isASCIIHex(value byte) bool {
	return '0' <= value && value <= '9' || 'a' <= value && value <= 'f' || 'A' <= value && value <= 'F'
}

func isCSSWhitespaceByte(value byte) bool {
	return value == ' ' || value == '\t' || value == '\n' || value == '\r' || value == '\f'
}
