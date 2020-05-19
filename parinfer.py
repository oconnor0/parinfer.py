## Parinfer.py - a Parinfer implementation in Python
## v3.12.0
## https://github.com/oakmac/parinfer.py
##
## More information about Parinfer can be found here:
## http://shaunlebron.github.io/parinfer/
##
## Copyright (c) 2015, 2020, Chris Oakman and other contributors
## Released under the ISC license
## https://github.com/oakmac/parinfer.py/blob/master/LICENSE.md

import re
import sys

def p(*args, **kwargs):
    # print(*args, **kwargs)
    return

#-------------------------------------------------------------------------------
# Constants
#-------------------------------------------------------------------------------

UINT_NULL = -999

INDENT_MODE = 'INDENT_MODE'
PAREN_MODE = 'PAREN_MODE'

BACKSLASH = '\\'
BLANK_SPACE = ' '
DOUBLE_SPACE = '  '
DOUBLE_QUOTE = '"'
NEWLINE = '\n'
SEMICOLON = ';'
TAB = '\t'

LINE_ENDING_REGEX = re.compile(r"\r?\n")

# CLOSE_PARENS = frozenset(['}', ')', ']'])

MATCH_PAREN = {
    '{': '}',
    '}': '{',
    '[': ']',
    ']': '[',
    '(': ')',
    ')': '(',
}

# toggle this to check the asserts during development
RUN_ASSERTS = False

#-------------------------------------------------------------------------------
# Options Structure
#-------------------------------------------------------------------------------

def transformChange(change):
    p("transformChange")
    if not change:
        return None

    newLines = re.split(LINE_ENDING_REGEX, change['newText'])
    oldLines = re.split(LINE_ENDING_REGEX, change['oldText'])

    # single line case:
    #    (defn foo| [])
    #             ^ newEndX, newEndLineNo
    #          +++

    # multi line case:
    #    (defn foo
    #          ++++
    #       "docstring."
    #    ++++++++++++++++
    #      |[])
    #    ++^ newEndX, newEndLineNo

    lastOldLineLen = len(oldLines[len(oldLines)-1])
    lastNewLineLen = len(newLines[len(newLines)-1])

    oldEndX = (change['x'] if len(oldLines) == 1 else 0) + lastOldLineLen
    newEndX = (change['x'] if len(newLines) == 1 else 0) + lastNewLineLen
    newEndLineNo = change['lineNo'] + (len(newLines)-1)

    return {
        'x': change['x'],
        'lineNo': change['lineNo'],
        'oldText': change['oldText'],
        'newText': change['newText'],

        'oldEndX': oldEndX,
        'newEndX': newEndX,
        'newEndLineNo': newEndLineNo,

        'lookupLineNo': newEndLineNo,
        'lookupX': newEndX
    }

def transformChanges(changes):
    p("transformChanges")
    if len(changes) == 0:
        return None

    lines = {}
    for change in changes:
        change = transformChange(change)
        # print("change:",change['lookupLineNo'])
        if change['lookupLineNo'] not in lines:
            line = lines[change['lookupLineNo']] = {}
        else:
            line = lines[change['lookupLineNo']]

        line[change['lookupX']] = change

    return lines

#-------------------------------------------------------------------------------
# Result Structure
#-------------------------------------------------------------------------------

# This represents the running result. As we scan through each character
# of a given text, we mutate this structure to update the state of our
# system.

class Clamped(object):
    __slots__ = ('startX', 'endX', 'openers')
    def __init__(self):
        p("Clamped __init__")
        self.startX = UINT_NULL       # startX before paren trail was clamped
        self.endX = UINT_NULL         # endX before paren trail was clamped
        self.openers = []             # openers that were cut out after paren trail was clamped

class ParenTrail(object):
    __slots__ = ('lineNo', 'startX', 'endX', 'openers', 'clamped')
    def __init__(self):
        p("ParenTrail __init__")
        self.lineNo = UINT_NULL       # [integer] - line number of the last parsed paren trail
        self.startX = UINT_NULL       # [integer] - x position of first paren in this range
        self.endX = UINT_NULL         # [integer] - x position after the last paren in this range
        self.openers = []             # [array of stack elements] - corresponding open-paren for each close-paren in this range
        self.clamped = Clamped()

def initialParenTrail():
    p("initialParenTrail")
    return ParenTrail()

class Result:
    """Returns a dictionary of the initial state."""
    __slots__ = (
        'mode', 'smart',
        'origText', 'origCursorX', 'origCursorLine',
        'inputLines',
        'inputLineNo', 'inputX',
        'lines', 'lineNo', 'ch', 'x', 'indentX',
        'parenStack',
        'tabStops', 'parenTrail',
        'parenTrails',
        'returnParens', 'parens',
        'cursorX', 'cursorLine', 'prevCursorX', 'prevCursorLine',
        'selectionStartLine',
        'changes',
        'isInCode', 'isEscaping', 'isEscaped', 'isInStr', 'isInComment',
        'commentX',
        'quoteDanger', 'trackingIndent', 'skipChar', 'success', 'partialResult',
        'forceBalance', 'maxIndent', 'indentDelta', 'trackingArgTabStop',
        'error',
        'errorPosCache')

    def __str__(self):
        return ('Result {' + 'mode: ' + str(self.mode) + '\n\t'
                'smart: ' + str(self.smart) + '\n\t'
                'origText: ' + str(self.origText) + '\n\t'
                'origCursorX: ' + str(self.origCursorX) + '\n\t'
                'origCursorLine: ' + str(self.origCursorLine) + '\n\t'
                'inputLines: ' + str(self.inputLines) + '\n\t'
                'inputLineNo: ' + str(self.inputLineNo) + '\n\t'
                'inputX: ' + str(self.inputX) + '\n\t'
                'lines: ' + str(self.lines) + '\n\t'
                'lineNo: ' + str(self.lineNo) + '\n\t'
                'ch: ' + str(self.ch) + '\n\t'
                'x: ' + str(self.x) + '\n\t'
                'indentX: ' + str(self.indentX) + '\n\t'
                'parenStack: ' + str(self.parenStack) + '\n\t'
                'tabStops: ' + str(self.tabStops) + '\n\t'
                'parenTrail: ' + str(self.parenTrail) + '\n\t'
                'parenTrails: ' + str(self.parenTrails) + '\n\t'
                'returnParens: ' + str(self.returnParens) + '\n\t'
                'parens: ' + str(self.parens) + '\n\t'
                'cursorX: ' + str(self.cursorX) + '\n\t'
                'cursorLine: ' + str(self.cursorLine) + '\n\t'
                'prevCursorX: ' + str(self.prevCursorX) + '\n\t'
                'prevCursorLine: ' + str(self.prevCursorLine) + '\n\t'
                'selectionStartLine: ' + str(self.selectionStartLine) + '\n\t'
                'changes: ' + str(self.changes) + '\n\t'
                'isInCode: ' + str(self.isInCode) + '\n\t'
                'isEscaping: ' + str(self.isEscaping) + '\n\t'
                'isEscaped: ' + str(self.isEscaped) + '\n\t'
                'isInStr: ' + str(self.isInStr) + '\n\t'
                'isInComment: ' + str(self.isInComment) + '\n\t'
                'commentX: ' + str(self.commentX) + '\n\t'
                'quoteDanger: ' + str(self.quoteDanger) + '\n\t'
                'trackingIndent: ' + str(self.trackingIndent) + '\n\t'
                'skipChar: ' + str(self.skipChar) + '\n\t'
                'success: ' + str(self.success) + '\n\t'
                'partialResult: ' + str(self.partialResult) + '\n\t'
                'forceBalance: ' + str(self.forceBalance) + '\n\t'
                'maxIndent: ' + str(self.maxIndent) + '\n\t'
                'indentDelta: ' + str(self.indentDelta) + '\n\t'
                'trackingArgTabStop: ' + str(self.trackingArgTabStop) + '\n\t'
                'error: ' + str(self.error) + '\n\t'
                'errorPosCache: ' + str(self.errorPosCache) + '\n\t}')

    def __init__(self, text, options, mode, smart):
        p("Result __init__")
        super(Result, self).__init__()

        self.mode = mode                # [enum] - current processing mode (INDENT_MODE or PAREN_MODE)
        self.smart = smart              # [boolean] - smart mode attempts special user-friendly behavior

        self.origText = text            # [string] - original text
        self.origCursorX = UINT_NULL    # [integer] - original cursorX option
        self.origCursorLine = UINT_NULL # [integer] - original cursorLine option

                                        # [string array] - input lines that we process line-by-line char-by-char
        self.inputLines = re.split(LINE_ENDING_REGEX, text)
        
        self.inputLineNo = -1           # [integer] - the current input line number
        self.inputX = -1                # [integer] - the current input x position of the current character (ch)

        self.lines = []                 # [string array] - output lines (with corrected parens or indentation)
        self.lineNo = -1                # [integer] - output line number we are on
        self.ch = ''                    # [string] - character we are processing (can be changed to indicate a replacement)
        self.x = 0                      # [integer] - output x position of the current character (ch)
        self.indentX = UINT_NULL        # [integer] - x position of the indentation point if present

        self.parenStack = []            # We track where we are in the Lisp tree by keeping a stack (array) of open-parens.
                                        # Stack elements are objects containing keys {ch, x, lineNo, indentDelta}
                                        # whose values are the same as those described here in this result structure.

        self.tabStops = []              # In Indent Mode, it is useful for editors to snap a line's indentation
                                        # to certain critical points.  Thus, we have a `tabStops` array of objects containing
                                        # keys {ch, x, lineNo, argX}, which is just the state of the `parenStack` at the cursor line.

        self.parenTrail = initialParenTrail() # the range of parens at the end of a line

        self.parenTrails = []           # [array of {lineNo, startX, endX}] - all non-empty parenTrails to be returned

        self.returnParens = False       # [boolean] - determines if we return `parens` described below
        self.parens = []                # [array of {lineNo, x, closer, children}] - paren tree if `returnParens` is h

        self.cursorX = UINT_NULL        # [integer] - x position of the cursor
        self.cursorLine = UINT_NULL     # [integer] - line number of the cursor
        self.prevCursorX = UINT_NULL    # [integer] - x position of the previous cursor
        self.prevCursorLine = UINT_NULL # [integer] - line number of the previous cursor

        self.selectionStartLine = UINT_NULL # [integer] - line number of the current selection starting point

        self.changes = None             # [object] - mapping change.key to a change object (please see `transformChange` for object structure)

        self.isInCode = True            # [boolean] - indicates if we are currently in "code space" (not string or comment)
        self.isEscaping = False         # [boolean] - indicates if the next character will be escaped (e.g. `\c`).  This may be inside string comment or code.
        self.isEscaped = False          # [boolean] - indicates if the current character is escaped (e.g. `\c`).  This may be inside string comment or code.
        self.isInStr = False            # [boolean] - indicates if we are currently inside a string
        self.isInComment = False        # [boolean] - indicates if we are currently inside a comment
        self.commentX = UINT_NULL       # [integer] - x position of the start of comment on current line (if any)

        self.quoteDanger = False        # [boolean] - indicates if quotes are imbalanced inside of a comment (dangerous)
        self.trackingIndent = False     # [boolean] - are we looking for the indentation point of the current line?
        self.skipChar = False           # [boolean] - should we skip the processing of the current character?
        self.success = False            # [boolean] - was the input properly formatted enough to create a valid result?
        self.partialResult = False      # [boolean] - should we return a partial result when an error occurs?
        self.forceBalance = False       # [boolean] - should indent mode aggressively enforce paren balance?

        self.maxIndent = UINT_NULL      # [integer] - maximum allowed indentation of subsequent lines in Paren Mode
        self.indentDelta = 0            # [integer] - how far indentation was shifted by Paren Mode
                                        #  (preserves relative indentation of nested expressions)

        self.trackingArgTabStop = None  # [string] - enum to track how close we are to the first-arg tabStop in a list
                                        #  For example a tabStop occurs at `bar` below:
                                        #
                                        #         `   (foo    bar`
                                        #          00011112222000  <-- state after processing char (enums below)
                                        #
                                        #         0   None    => not searching
                                        #         1   'space' => searching for next space
                                        #         2   'arg'   => searching for arg
                                        #
                                        #    (We create the tabStop when the change from 2->0 happens.)
                                        #

        self.error = {                  # if 'success' is False, return this error to the user
            'name': None,               # [string] - Parinfer's unique name for this error
            'message': None,            # [string] - error message to display
            'lineNo': None,             # [integer] - line number of error
            'x': None,                  # [integer] - start x position of error
            'extra': {
                'name': None,
                'lineNo': None,
                'x': None
            }
        }
        self.errorPosCache = {}         # [object] - maps error name to a potential error position

        if isinstance(options, dict):
            if 'cursorX' in options:
                self.cursorX = options['cursorX']
                self.origCursorX = options['cursorX']
            if 'cursorLine' in options:
                self.cursorLine = options['cursorLine']
                self.origCursorLine     = options['cursorLine']
            if 'prevCursorX' in options:
                self.prevCursorX = options['prevCursorX']
            if 'prevCursorLine' in options:
                self.prevCursorLine = options['prevCursorLine']
            if 'selectionStartLine' in options:
                self.selectionStartLine = options['selectionStartLine']
            if 'changes' in options:
                self.changes = transformChanges(options['changes'])
            if 'partialResult' in options:
                self.partialResult = options['partialResult']
            if 'forceBalance' in options:
                self.forceBalance = options['forceBalance']
            if 'returnParens' in options:
                self.returnParens = options['returnParens']

def getInitialResult(text, options, mode, smart):
    p("getInitialResult")
    """Returns a dictionary of the initial state."""

    return Result(text, options, mode, smart)

#-------------------------------------------------------------------------------
# Possible Errors
#-------------------------------------------------------------------------------

# `result.error.name` is set to any of these
ERROR_QUOTE_DANGER = "quote-danger"
ERROR_EOL_BACKSLASH = "eol-backslash"
ERROR_UNCLOSED_QUOTE = "unclosed-quote"
ERROR_UNCLOSED_PAREN = "unclosed-paren"
ERROR_UNMATCHED_CLOSE_PAREN = "unmatched-close-paren"
ERROR_UNMATCHED_OPEN_PAREN = "unmatched-open-paren"
ERROR_LEADING_CLOSE_PAREN = "leading-close-paren"
ERROR_UNHANDLED = "unhandled"

errorMessages = {}
errorMessages[ERROR_QUOTE_DANGER] = "Quotes must balanced inside comment blocks."
errorMessages[ERROR_EOL_BACKSLASH] = "Line cannot end in a hanging backslash."
errorMessages[ERROR_UNCLOSED_QUOTE] = "String is missing a closing quote."
errorMessages[ERROR_UNCLOSED_PAREN] = "Unclosed open-paren."
errorMessages[ERROR_UNMATCHED_CLOSE_PAREN] = "Unmatched close-paren."
errorMessages[ERROR_UNMATCHED_OPEN_PAREN] = "Unmatched open-paren."
errorMessages[ERROR_LEADING_CLOSE_PAREN] = "Line cannot lead with a close-paren."
errorMessages[ERROR_UNHANDLED] = "Unhandled error."

def cacheErrorPos(result, errorName):
    p("cacheErrorPos")
    e = {
        'lineNo': result.lineNo,
        'x': result.x,
        'inputLineNo': result.inputLineNo,
        'inputX': result.inputX
    }
    result.errorPosCache[errorName] = e
    return e

class ParinferError(Exception):
    pass

def error(result, name):
    p("error")
    cache = {}
    if name in result.errorPosCache:
        cache = result.errorPosCache[name]

    resultLineNo = result.LineNo if result.partialResult else result.inputLineNo
    resultX = result.x if result.partialResult else result.inputX

    keyLineNo = 'lineNo' if result.partialResult else 'inputLineNo'
    keyX = 'x' if result.partialResult else 'inputX'

    e = {
        'parinferError': True,
        'name': name,
        'message': errorMessages[name],
        'lineNo': cache[keyLineNo] if cache else resultLineNo,
        'x': cache[keyX] if cache else resultX
    }
    opener = peek(result.parenStack, 0)

    # p("result.partialResult",result.partialResult, file=sys.stderr)

    if name == ERROR_UNMATCHED_CLOSE_PAREN:
        # extra error info for locating the open-paren that it should've matched

        if ERROR_UNMATCHED_OPEN_PAREN in result.errorPosCache:
            cache = result.errorPosCache[ERROR_UNMATCHED_OPEN_PAREN]

        if cache or opener:
            if opener:
                openerLineNo = opener.LineNo if result.partialResult else opener.inputLineNo
                openerX = opener.x if result.partialResult else opener.inputX

            e['extra'] = {
                'name': ERROR_UNMATCHED_OPEN_PAREN,
                'lineNo': cache[keyLineNo] if cache else openerLineNo,
                'x': cache[keyX] if cache else openerX
            }
    elif name == ERROR_UNCLOSED_PAREN:
        openerLineNo = opener.LineNo if result.partialResult else opener.inputLineNo
        openerX = opener.x if result.partialResult else opener.inputX

        e['lineNo'] = openerLineNo
        e['x'] = openerX

    return ParinferError(e)

#-------------------------------------------------------------------------------
# String Operations
#-------------------------------------------------------------------------------

def replaceWithinString(orig, start, end, replace):
    p("replaceWithinString")
    return orig[:start] + replace + orig[end:]

if RUN_ASSERTS:
    assert replaceWithinString('aaa', 0, 2, '') == 'a'
    assert replaceWithinString('aaa', 0, 1, 'b') == 'baa'
    assert replaceWithinString('aaa', 0, 2, 'b') == 'ba'

def repeatString(text, n):
    p("repeatString")
    return text*n

if RUN_ASSERTS:
    assert repeatString('a', 2) == 'aa'
    assert repeatString('aa', 3) == 'aaaaaa'
    assert repeatString('aa', 0) == ''
    assert repeatString('', 0) == ''
    assert repeatString('', 5) == ''

def getLineEnding(text):
    p("getLineEnding")
    # NOTE: We assume that if the CR char "\r" is used anywhere,
    #       then we should use CRLF line-endings after every line.
    i = text.find("\r")
    if i != -1:
        return "\r\n"
    return "\n"

#-------------------------------------------------------------------------------
# Line Operations
#-------------------------------------------------------------------------------

def isCursorAffected(result, start, end):
    p("isCursorAffected")
    if result.cursorX == start and result.cursorX == end:
        return result.cursorX == 0
    return result.cursorX >= end

def shiftCursorOnEdit(result, lineNo, start, end, replace):
    p("shiftCursorOnEdit")
    oldLength = end - start
    newLength = len(replace)
    dx = newLength - oldLength

    if (dx != 0 and
            result.cursorLine == lineNo and
            result.cursorX != UINT_NULL and
            isCursorAffected(result, start, end)):
        result.cursorX += dx

def replaceWithinLine(result, lineNo, start, end, replace):
    p("replaceWithinLine(result",lineNo,start,end,replace,")")
    line = result.lines[lineNo]
    newLine = replaceWithinString(line, start, end, replace)
    result.lines[lineNo] = newLine

    shiftCursorOnEdit(result, lineNo, start, end, replace)

def insertWithinLine(result, lineNo, idx, insert):
    p("insertWithinLine")
    replaceWithinLine(result, lineNo, idx, idx, insert)

def initLine(result):
    p("initLine")
    result.x = 0
    result.lineNo += 1

    # reset line-specific state
    result.indentX = UINT_NULL
    result.commentX = UINT_NULL
    result.indentDelta = 0
    if ERROR_UNMATCHED_CLOSE_PAREN in result.errorPosCache:
        del result.errorPosCache[ERROR_UNMATCHED_CLOSE_PAREN]
    if ERROR_UNMATCHED_OPEN_PAREN in result.errorPosCache:
        del result.errorPosCache[ERROR_UNMATCHED_OPEN_PAREN]
    if ERROR_LEADING_CLOSE_PAREN in result.errorPosCache:
        del result.errorPosCache[ERROR_LEADING_CLOSE_PAREN]

    result.trackingArgTabStop = None
    result.trackingIndent = not result.isInStr

# if the current character has changed, commit its change to the current line.
def commitChar(result, origCh):
    p("commitChar")
    ch = result.ch
    if origCh != ch:
        replaceWithinLine(result, result.lineNo, result.x, result.x + len(origCh), ch)
        result.indentDelta -= (len(origCh) - len(ch))
    result.x += len(ch)

#-------------------------------------------------------------------------------
# Misc Utils
#-------------------------------------------------------------------------------

def clamp(val, minN, maxN):
    p("clamp")
    if minN != UINT_NULL:
        val = max(minN, val)
    if maxN != UINT_NULL:
        val = min(maxN, val)
    return val

if RUN_ASSERTS:
    assert clamp(1, 3, 5) == 3
    assert clamp(9, 3, 5) == 5
    assert clamp(1, 3, UINT_NULL) == 3
    assert clamp(5, 3, UINT_NULL) == 5
    assert clamp(1, UINT_NULL, 5) == 1
    assert clamp(9, UINT_NULL, 5) == 5
    assert clamp(1, UINT_NULL, UINT_NULL) == 1

def peek(arr, idxFromBack):
    p("peek(",len(arr),idxFromBack,")")
    maxIdx = len(arr) - 1
    if idxFromBack > maxIdx:
        return None
    return arr[maxIdx - idxFromBack]

if RUN_ASSERTS:
    assert peek(['a'], 0) == 'a'
    assert peek(['a'], 1) == None
    assert peek(['a', 'b', 'c'], 0) == 'c'
    assert peek(['a', 'b', 'c'], 1) == 'b'
    assert peek(['a', 'b', 'c'], 5) == None
    assert peek([], 0) == None
    assert peek([], 1) == None

#-------------------------------------------------------------------------------
# Questions about characters
#-------------------------------------------------------------------------------

def isOpenParen(ch):
    p("isOpenParen")
    return ch == '{' or ch == '(' or ch == '['

def isCloseParen(ch):
    p("isCloseParen")
    return ch == '}' or ch == ')' or ch == ']'
    # return ch in CLOSE_PARENS

def isValidCloseParen(parenStack, ch):
    p("isValidCloseParen")
    if len(parenStack) == 0:
        return False
    return peek(parenStack, 0).ch == MATCH_PAREN[ch]

def isWhitespace(result):
    p("isWhitespace")
    ch = result.ch
    # return not result.isEscaped and (ch == BLANK_SPACE or ch == DOUBLE_SPACE)
    return not result.isEscaped and ch in (BLANK_SPACE, DOUBLE_SPACE)

# can this be the last code character of a list?
def isClosable(result):
    p("isClosable")
    ch = result.ch
    closer = isCloseParen(ch) and not result.isEscaped
    # closer = ch in ('}', ')', ']') and not result.isEscaped
    return result.isInCode and not isWhitespace(result) and ch != '' and not closer
    # return result.isInCode and not ch in (BLANK_SPACE, DOUBLE_SPACE) and ch != '' and not closer


#-------------------------------------------------------------------------------
# Advanced operations on characters
#-------------------------------------------------------------------------------

def checkCursorHolding(result):
    p("checkCursorHolding")
    opener = peek(result.parenStack, 0)
    parent = peek(result.parenStack, 1)
    holdMinX = parent.x+1 if parent else 0
    holdMaxX = opener.x

    holding = (
        result.cursorLine == opener.lineNo and
        holdMinX <= result.cursorX and result.cursorX <= holdMaxX
    )
    shouldCheckPrev = not result.changes and result.prevCursorLine != UINT_NULL
    if shouldCheckPrev:
        prevHolding = (
            result.prevCursorLine == opener.lineNo and
            holdMinX <= result.prevCursorX and result.prevCursorX <= holdMaxX
        )
        if prevHolding and not holding:
            raise ParinferError({'releaseCursorHold': True})
    return holding

def trackArgTabStop(result, state):
    p("trackArgTabStop")
    if state == 'space':
        if result.isInCode and isWhitespace(result):
            result.trackingArgTabStop = 'arg'
    elif state == 'arg':
        if not isWhitespace(result):
            opener = peek(result.parenStack, 0)
            opener.argX = result.x
            result.trackingArgTabStop = None

#-------------------------------------------------------------------------------
# Literal character events
#-------------------------------------------------------------------------------

class Opener(object):
    __slots__ = ('self', 'inputLineNo', 'inputX', 'lineNo', 'x', 'ch', 'indentDelta', 'maxChildIndent', 'argX')
    def __init__(self, inputLineNo, inputX, lineNo, x, ch, indentDelta, maxChildIndent):
        p("Opener __init__")
        super(Opener, self).__init__()
        self.inputLineNo = inputLineNo
        self.inputX = inputX
        self.lineNo = lineNo
        self.x = x
        self.ch = ch
        self.indentDelta = indentDelta
        self.maxChildIndent = maxChildIndent
        self.argX = None

    def __str__(self):
        return ("{ inputLineNo: " + str(self.inputLineNo)
            + "\n  inputX: " + str(self.inputX)
            + "\n  lineNo: " + str(self.lineNo)
            + "\n  x: " + str(self.x)
            + "\n  ch: " + str(self.ch)
            + "\n  indentDelta: " + str(self.indentDelta)
            + "\n  maxChildIndent: " + str(self.maxChildIndent)
            + "}")

        # opener = {
        #     'inputLineNo': result.inputLineNo,
        #     'inputX': result.inputX,

        #     'lineNo': result.lineNo,
        #     'x': result.x,
        #     'ch': result.ch,
        #     'indentDelta': result.indentDelta,
        #     'maxChildIndent': UINT_NULL
        # }

def onOpenParen(result):
    p("onOpenParen")
    if result.isInCode:
        opener = Opener(
            result.inputLineNo,
            result.inputX,
            result.lineNo,
            result.x,
            result.ch,
            result.indentDelta,
            UINT_NULL
        )

        if result.returnParens:
            opener.children = []
            opener.closer = {
                lineNo: UINT_NULL,
                x: UINT_NULL,
                ch: ''
            }
            parent = peek(result.parenStack, 0)
            parent = parent.children if parent else result.parens
            parent.append(opener)

        result.parenStack.append(opener)
        result.trackingArgTabStop = 'space'

def setCloser(opener, lineNo, x, ch):
    p("setCloser")
    opener.closer.lineNo = lineNo
    opener.closer.x = x
    opener.closer.ch = ch

def onMatchedCloseParen(result):
    p("onMatchedCloseParen")
    opener = peek(result.parenStack, 0)
    if result.returnParens:
        setCloser(opener, result.lineNo, result.x, result.ch)

    result.parenTrail.endX = result.x + 1
    result.parenTrail.openers.append(opener)

    if result.mode == INDENT_MODE and result.smart and checkCursorHolding(result):
        origStartX = result.parenTrail.startX
        origEndX = result.parenTrail.endX
        origOpeners = result.parenTrail.openers
        resetParenTrail(result, result.lineNo, result.x+1)
        result.parenTrail.clamped.startX = origStartX
        result.parenTrail.clamped.endX = origEndX
        result.parenTrail.clamped.openers = origOpeners

    result.parenStack.pop()
    result.trackingArgTabStop = None

def onUnmatchedCloseParen(result):
    p("onUnmatchedCloseParen")
    if result.mode == PAREN_MODE:
        trail = result.parenTrail
        inLeadingParenTrail = trail.lineNo == result.lineNo and trail.startX == result.indentX
        canRemove = result.smart and inLeadingParenTrail
        if not canRemove:
            raise error(result, ERROR_UNMATCHED_CLOSE_PAREN)
    elif result.mode == INDENT_MODE and (
            ERROR_UNMATCHED_CLOSE_PAREN not in result.errorPosCache):
        cacheErrorPos(result, ERROR_UNMATCHED_CLOSE_PAREN)
        opener = peek(result.parenStack, 0)
        if opener:
            e = cacheErrorPos(result, ERROR_UNMATCHED_OPEN_PAREN)
            e['inputLineNo'] = opener.inputLineNo
            e['inputX'] = opener.inputX

    result.ch = ''

def onCloseParen(result):
    p("onCloseParen")
    if result.isInCode:
        if isValidCloseParen(result.parenStack, result.ch):
            onMatchedCloseParen(result)
        else:
            onUnmatchedCloseParen(result)

def onTab(result):
    p("onTab")
    if result.isInCode:
        result.ch = DOUBLE_SPACE

def onSemicolon(result):
    p("onSemicolon")
    if result.isInCode:
        result.isInComment = True
        result.commentX = result.x
        result.trackingArgTabStop = None

def onNewline(result):
    p("onNewline")
    result.isInComment = False
    result.ch = ''

def onQuote(result):
    p("onQuote")
    if result.isInStr:
        result.isInStr = False
    elif result.isInComment:
        result.quoteDanger = not result.quoteDanger
        if (result.quoteDanger):
            cacheErrorPos(result, ERROR_QUOTE_DANGER)
    else:
        result.isInStr = True
        cacheErrorPos(result, ERROR_UNCLOSED_QUOTE)

def onBackslash(result):
    p("onBackslash")
    result.isEscaping = True

def afterBackslash(result):
    p("afterBackslash")
    result.isEscaping = False
    result.isEscaped = True

    if result.ch == NEWLINE:
        if result.isInCode:
            raise error(result, ERROR_EOL_BACKSLASH)
        onNewline(result)

#-------------------------------------------------------------------------------
# Character dispatch
#-------------------------------------------------------------------------------

def onChar(result):
    p("onChar")
    ch = result.ch
    result.isEscaped = False

    if result.isEscaping:
        afterBackslash(result)
    elif isOpenParen(ch):
        onOpenParen(result)
    elif isCloseParen(ch):
        onCloseParen(result)
    elif ch == DOUBLE_QUOTE:
        onQuote(result)
    elif ch == SEMICOLON:
        onSemicolon(result)
    elif ch == BACKSLASH:
        onBackslash(result)
    elif ch == TAB:
        onTab(result)
    elif ch == NEWLINE:
        onNewline(result)

    ch = result.ch

    result.isInCode = not result.isInComment and not result.isInStr

    if isClosable(result):
        resetParenTrail(result, result.lineNo, result.x+len(ch))

    state = result.trackingArgTabStop
    if (state):
        trackArgTabStop(result, state)

#-------------------------------------------------------------------------------
# Cursor defs
#-------------------------------------------------------------------------------

def isCursorLeftOf(cursorX, cursorLine, x, lineNo):
    p("isCursorLeftOf")
    return (
        cursorLine == lineNo and
        x != UINT_NULL and
        cursorX != UINT_NULL and
        cursorX <= x # inclusive since (cursorX = x) implies (x-1 < cursor < x)
    )

def isCursorRightOf(cursorX, cursorLine, x, lineNo):
    p("isCursorRightOf")
    return (
        cursorLine == lineNo and
        x != UINT_NULL and
        cursorX != UINT_NULL and
        cursorX > x
    )

def isCursorInComment(result, cursorX, cursorLine):
    p("isCursorInComment")
    return isCursorRightOf(cursorX, cursorLine, result.commentX, result.lineNo)

def handleChangeDelta(result):
    p("handleChangeDelta")
    if (result.changes and (result.smart or result.mode == PAREN_MODE)):
        if result.inputLineNo in result.changes:
            line = result.changes[result.inputLineNo]
            if result.inputX in line:
                change = line[result.inputX]
                result.indentDelta += (change['newEndX'] - change['oldEndX'])

#-------------------------------------------------------------------------------
# Paren Trail defs
#-------------------------------------------------------------------------------

def resetParenTrail(result, lineNo, x):
    p("resetParenTrail")
    result.parenTrail.lineNo = lineNo
    result.parenTrail.startX = x
    result.parenTrail.endX = x
    result.parenTrail.openers = []
    result.parenTrail.clamped.startX = UINT_NULL
    result.parenTrail.clamped.endX = UINT_NULL
    result.parenTrail.clamped.openers = []

def isCursorClampingParenTrail(result, cursorX, cursorLine):
    p("isCursorClampingParenTrail")
    return (
        isCursorRightOf(cursorX, cursorLine, result.parenTrail.startX, result.lineNo) and
        not isCursorInComment(result, cursorX, cursorLine)
    )

# INDENT MODE: allow the cursor to clamp the paren trail
def clampParenTrailToCursor(result):
    p("clampParenTrailToCursor")
    startX = result.parenTrail.startX
    endX = result.parenTrail.endX

    clamping = isCursorClampingParenTrail(result, result.cursorX, result.cursorLine)

    if clamping:
        newStartX = max(startX, result.cursorX)
        newEndX = max(endX, result.cursorX)

        line = result.lines[result.lineNo]
        p("clamp line", line, startX, newStartX)
        removeCount = 0
        for i in range(startX, newStartX):
            if isCloseParen(line[i]):
                removeCount += 1

        openers = result.parenTrail.openers

        result.parenTrail.openers = openers[removeCount:]
        result.parenTrail.startX = newStartX
        result.parenTrail.endX = newEndX

        result.parenTrail.clamped.openers = openers[0:removeCount]
        result.parenTrail.clamped.startX = startX
        result.parenTrail.clamped.endX = endX

# INDENT MODE: pops the paren trail from the stack
def popParenTrail(result):
    p("popParenTrail")
    startX = result.parenTrail.startX
    endX = result.parenTrail.endX

    if startX == endX:
        return

    openers = result.parenTrail.openers
    while len(openers) != 0:
        result.parenStack.append(openers.pop())

# Determine which open-paren (if any) on the parenStack should be considered
# the direct parent of the current line (given its indentation point).
# This allows Smart Mode to simulate Paren Mode's structure-preserving
# behavior by adding its `opener.indentDelta` to the current line's indentation.
# (care must be taken to prevent redundant indentation correction, detailed below)
def getParentOpenerIndex(result, indentX):
    p("getParentOpenerIndex(result,",indentX,")")
    i = 0
    p("range(len(result.parenStack))",range(len(result.parenStack)))
    # for i in range(len(result.parenStack)):
    parenStackLen = len(result.parenStack)
    while i < parenStackLen:
        # idx = i
        opener = peek(result.parenStack, i)
        p("    opener",opener)

        currOutside = (opener.x < indentX)

        prevIndentX = indentX - result.indentDelta
        prevOutside = (opener.x - opener.indentDelta < prevIndentX)

        isParent = False

        p("currOutside",currOutside,"prevIndentX",prevIndentX,"prevOutside",prevOutside)

        if prevOutside and currOutside:
            p("prevOutside and currOutside")
            isParent = True
        elif not prevOutside and not currOutside:
            p("not prevOutside and not currOutside")
            isParent = False
        elif prevOutside and not currOutside:
            p("prevOutside and not currOutside")
            # POSSIBLE FRAGMENTATION
            # (foo    --\
            #            +--- FRAGMENT `(foo bar)` => `(foo) bar`
            # bar)    --/

            # 1. PREVENT FRAGMENTATION
            # ```in
            #   (foo
            # ++
            #   bar
            # ```
            # ```out
            #   (foo
            #     bar
            # ```
            if result.indentDelta == 0:
                p("result.indentDelta == 0")
                isParent = True

            # 2. ALLOW FRAGMENTATION
            # ```in
            # (foo
            #   bar
            # --
            # ```
            # ```out
            # (foo)
            # bar
            # ```
            elif opener.indentDelta == 0:
                p("opener.indentDelta == 0")
                isParent = False

            else:
                p("else")
                # TODO: identify legitimate cases where both are nonzero

                # allow the fragmentation by default
                isParent = False

                # TODO: should we throw to exit instead?  either of:
                # 1. give up, just `throw error(...)`
                # 2. fallback to paren mode to preserve structure
        elif not prevOutside and currOutside:
            p("not prevOutside and currOutside")
            # POSSIBLE ADOPTION
            # (foo)   --\
            #            +--- ADOPT `(foo) bar` => `(foo bar)`
            #   bar   --/

            nextOpener = peek(result.parenStack, i+1)

            # 1. DISALLOW ADOPTION
            # ```in
            #   (foo
            # --
            #     (bar)
            # --
            #     baz)
            # ```
            # ```out
            # (foo
            #   (bar)
            #   baz)
            # ```
            # OR
            # ```in
            #   (foo
            # --
            #     (bar)
            # -
            #     baz)
            # ```
            # ```out
            # (foo
            #  (bar)
            #  baz)
            # ```
            if nextOpener and nextOpener.indentDelta <= opener.indentDelta:
                p("nextOpener and nextOpener.indentDelta <= opener.indentDelta")
                # we can only disallow adoption if nextOpener.indentDelta will actually
                # prevent the indentX from being in the opener's threshold.
                if indentX + nextOpener.indentDelta > opener.x:
                    p("indentX + nextOpener.indentDelta > opener.x")
                    isParent = True
                else:
                    isParent = False

            # 2. ALLOW ADOPTION
            # ```in
            # (foo
            #     (bar)
            # --
            #     baz)
            # ```
            # ```out
            # (foo
            #   (bar
            #     baz))
            # ```
            # OR
            # ```in
            #   (foo
            # -
            #     (bar)
            # --
            #     baz)
            # ```
            # ```out
            #  (foo
            #   (bar)
            #    baz)
            # ```
            elif nextOpener and nextOpener.indentDelta > opener.indentDelta:
                p("nextOpener and nextOpener.indentDelta > opener.indentDelta")
                isParent = True

            # 3. ALLOW ADOPTION
            # ```in
            #   (foo)
            # --
            #   bar
            # ```
            # ```out
            # (foo
            #   bar)
            # ```
            # OR
            # ```in
            # (foo)
            #   bar
            # ++
            # ```
            # ```out
            # (foo
            #   bar
            # ```
            # OR
            # ```in
            #  (foo)
            # +
            #   bar
            # ++
            # ```
            # ```out
            #  (foo
            #   bar)
            # ```
            elif result.indentDelta > opener.indentDelta:
                p("result.indentDelta > opener.indentDelta")
                isParent = True

            if isParent: # if new parent
                # Clear `indentDelta` since it is reserved for previous child lines only.
                opener.indentDelta = 0

        if isParent:
            p("    isParent",i)
            # p("    i",i)
            # return i
            break

        i += 1

    p("    i",i)
    return i

# INDENT MODE: correct paren trail from indentation
def correctParenTrail(result, indentX):
    p("correctParenTrail")
    parens = ''

    index = getParentOpenerIndex(result, indentX)
    for i in range(index):
        opener = result.parenStack.pop()
        result.parenTrail.openers.append(opener)
        closeCh = MATCH_PAREN[opener.ch]
        parens += closeCh

        if result.returnParens:
            setCloser(opener, result.parenTrail.lineNo, result.parenTrail.startX+i, closeCh)

    if result.parenTrail.lineNo != UINT_NULL:
        replaceWithinLine(result, result.parenTrail.lineNo, result.parenTrail.startX, result.parenTrail.endX, parens)
        result.parenTrail.endX = result.parenTrail.startX + len(parens)
        rememberParenTrail(result)

# PAREN MODE: remove spaces from the paren trail
def cleanParenTrail(result):
    p("cleanParenTrail")
    startX = result.parenTrail.startX
    endX = result.parenTrail.endX

    if (startX == endX or
        result.lineNo != result.parenTrail.lineNo):
        return

    line = result.lines[result.lineNo]
    newTrail = ''
    spaceCount = 0
    for i in range(startX, endX):
        if isCloseParen(line[i]):
            newTrail += line[i]
        else:
            spaceCount += 1

    if spaceCount > 0:
        replaceWithinLine(result, result.lineNo, startX, endX, newTrail)
        result.parenTrail.endX -= spaceCount

# PAREN MODE: append a valid close-paren to the end of the paren trail
def appendParenTrail(result):
    p("appendParenTrail")
    opener = result.parenStack.pop()
    closeCh = MATCH_PAREN[opener.ch]
    if result.returnParens:
        setCloser(opener, result.parenTrail.lineNo, result.parenTrail.endX, closeCh)

    setMaxIndent(result, opener)
    insertWithinLine(result, result.parenTrail.lineNo, result.parenTrail.endX, closeCh)

    result.parenTrail.endX += 1
    result.parenTrail.openers.append(opener)
    updateRememberedParenTrail(result)

def invalidateParenTrail(result):
    p("invalidateParenTrail")
    result.parenTrail = initialParenTrail()

def checkUnmatchedOutsideParenTrail(result):
    p("checkUnmatchedOutsideParenTrail")
    cache = None
    if ERROR_UNMATCHED_CLOSE_PAREN in result.errorPosCache:
        cache = result.errorPosCache[ERROR_UNMATCHED_CLOSE_PAREN]
    if cache and cache['x'] < result.parenTrail.startX:
        raise error(result, ERROR_UNMATCHED_CLOSE_PAREN)

def setMaxIndent(result, opener):
    p("setMaxIndent")
    if opener:
        parent = peek(result.parenStack, 0)
        if parent:
            parent.maxChildIndent = opener.x
        else:
            result.maxIndent = opener.x

def rememberParenTrail(result):
    p("rememberParenTrail")
    trail = result.parenTrail
    openers = trail.clamped.openers + trail.openers
    if len(openers) > 0:
        isClamped = trail.clamped.startX != UINT_NULL
        allClamped = len(trail.openers) == 0
        shortTrail = {
            'lineNo': trail.lineNo,
            'startX': trail.clamped.startX if isClamped else trail.startX,
            'endX': trail.clamped.endX if allClamped else trail.endX,
        }
        result.parenTrails.append(shortTrail)

        if result.returnParens:
            for i in range(len(openers)):
                openers[i].closer.trail = shortTrail

def updateRememberedParenTrail(result):
    p("updateRememberedParenTrail",len(result.parenTrails))
    if result.parenTrails:
        trail = result.parenTrails[len(result.parenTrails)-1]
        if trail['lineNo'] != result.parenTrail.lineNo:
            rememberParenTrail(result)
        else:
            trail['endX'] = result.parenTrail.endX
            if result.returnParens:
                opener = result.parenTrail.openers[len(result.parenTrail.openers)-1]
                opener.closer.trail = trail
    else:
        rememberParenTrail(result)

def finishNewParenTrail(result):
    p("finishNewParenTrail")
    if result.isInStr:
        invalidateParenTrail(result)
    elif result.mode == INDENT_MODE:
        clampParenTrailToCursor(result)
        popParenTrail(result)
    elif result.mode == PAREN_MODE:
        setMaxIndent(result, peek(result.parenTrail.openers, 0))
        if result.lineNo != result.cursorLine:
            cleanParenTrail(result)
        rememberParenTrail(result)

#-------------------------------------------------------------------------------
# Indentation defs
#-------------------------------------------------------------------------------

def addIndent(result, delta):
    p("addIndent")
    origIndent = result.x
    newIndent = origIndent + delta
    indentStr = repeatString(BLANK_SPACE, newIndent)
    replaceWithinLine(result, result.lineNo, 0, origIndent, indentStr)
    result.x = newIndent
    result.indentX = newIndent
    result.indentDelta += delta

def shouldAddOpenerIndent(result, opener):
    p("shouldAddOpenerIndent")
    # Don't add opener.indentDelta if the user already added it.
    # (happens when multiple lines are indented together)
    return opener.indentDelta != result.indentDelta

def correctIndent(result):
    p("correctIndent")
    origIndent = result.x
    newIndent = origIndent
    minIndent = 0
    maxIndent = result.maxIndent

    opener = peek(result.parenStack, 0)
    if opener:
        minIndent = opener.x + 1
        maxIndent = opener.maxChildIndent
        if shouldAddOpenerIndent(result, opener):
            newIndent += opener.indentDelta

    newIndent = clamp(newIndent, minIndent, maxIndent)

    if newIndent != origIndent:
        addIndent(result, newIndent - origIndent)

def onIndent(result):
    p("onIndent")
    result.indentX = result.x
    result.trackingIndent = False

    if result.quoteDanger:
        raise error(result, ERROR_QUOTE_DANGER)

    if result.mode == INDENT_MODE:

        correctParenTrail(result, result.x)

        opener = peek(result.parenStack, 0)
        if opener and shouldAddOpenerIndent(result, opener):
            addIndent(result, opener.indentDelta)
    elif result.mode == PAREN_MODE:
        correctIndent(result)

def checkLeadingCloseParen(result):
    p("checkLeadingCloseParen")
    if (ERROR_LEADING_CLOSE_PAREN in result.errorPosCache and
            result.parenTrail.lineNo == result.lineNo):
        raise error(result, ERROR_LEADING_CLOSE_PAREN)

def onLeadingCloseParen(result):
    p("onLeadingCloseParen")
    if result.mode == INDENT_MODE:
        if not result.forceBalance:
            if result.smart:
                raise ParinferError({'leadingCloseParen': True})
        if ERROR_LEADING_CLOSE_PAREN not in result.errorPosCache:
            cacheErrorPos(result, ERROR_LEADING_CLOSE_PAREN)
        result.skipChar = True

    if result.mode == PAREN_MODE:
        if not isValidCloseParen(result.parenStack, result.ch):
            if result.smart:
                result.skipChar = True
            else:
                raise error(result, ERROR_UNMATCHED_CLOSE_PAREN)
        elif isCursorLeftOf(result.cursorX, result.cursorLine, result.x, result.lineNo):
            resetParenTrail(result, result.lineNo, result.x)
            onIndent(result)
        else:
            appendParenTrail(result)
            result.skipChar = True

def onCommentLine(result):
    p("onCommentLine")
    parenTrailLength = len(result.parenTrail.openers)

    # restore the openers matching the previous paren trail
    if result.mode == PAREN_MODE:
        for j in range(parenTrailLength):
            result.parenStack.append(peek(result.parenTrail.openers, j))

    i = getParentOpenerIndex(result, result.x)
    opener = peek(result.parenStack, i)
    if opener:
        # shift the comment line based on the parent open paren
        if shouldAddOpenerIndent(result, opener):
            addIndent(result, opener.indentDelta)
        # TODO: store some information here if we need to place close-parens after comment lines

    # repop the openers matching the previous paren trail
    if result.mode == PAREN_MODE:
        for j in range(parenTrailLength):
            result.parenStack.pop()

def checkIndent(result):
    p("checkIndent")
    if isCloseParen(result.ch):
        onLeadingCloseParen(result)
    elif result.ch == SEMICOLON:
        # comments don't count as indentation points
        onCommentLine(result)
        result.trackingIndent = False
    elif (result.ch != NEWLINE and
            result.ch != BLANK_SPACE and
            result.ch != TAB):
        onIndent(result)

def makeTabStop(result, opener):
    p("makeTabStop")
    tabStop = {
        'ch': opener.ch,
        'x': opener.x,
        'lineNo': opener.lineNo
    }
    if opener.argX != None:
        tabStop['argX'] = opener.argX
    return tabStop

def getTabStopLine(result):
    p("getTabStopLine")
    return result.selectionStartLine if result.selectionStartLine != UINT_NULL else result.cursorLine

def setTabStops(result):
    p("setTabStops")
    if getTabStopLine(result) != result.lineNo:
        return

    for i in range(len(result.parenStack)):
        result.tabStops.append(makeTabStop(result, result.parenStack[i]))

    if result.mode == PAREN_MODE:
        for i in range(len(result.parenTrail.openers)-1, -1, -1):
            result.tabStops.append(makeTabStop(result, result.parenTrail.openers[i]))

    # remove argX if it falls to the right of the next stop
    for i in range(1, len(result.tabStops)):
        x = result.tabStops[i]['x']
        if 'argX' in result.tabStops[i-1] and result.tabStops[i-1]['argX'] >= x:
            del result.tabStops[i-1]['argX']

#-------------------------------------------------------------------------------
# High-level processing functions
#-------------------------------------------------------------------------------

def processChar(result, ch):
    p("processChar")
    origCh = ch

    result.ch = ch
    result.skipChar = False

    handleChangeDelta(result)

    if result.trackingIndent:
        checkIndent(result)

    if result.skipChar:
        result.ch = ''
    else:
        onChar(result)

    commitChar(result, origCh)

def processLine(result, lineNo):
    p("processLine")
    p(lineNo)
    initLine(result)
    result.lines.append(result.inputLines[lineNo])
    p("result.lines",result.lines)

    setTabStops(result)

    p("result.inputLines",result.inputLines)
    for x in range(0,len(result.inputLines[lineNo])):
        p("x",x)
        result.inputX = x
        processChar(result, result.inputLines[lineNo][x])
    p("result.lines",result.lines)
    p("result.inputLines",result.inputLines)
    processChar(result, NEWLINE)

    if not result.forceBalance:
        p("if not result.forceBalance:")
        checkUnmatchedOutsideParenTrail(result)
        checkLeadingCloseParen(result)

    if result.lineNo == result.parenTrail.lineNo:
        finishNewParenTrail(result)

def finalizeResult(result):
    p("finalizeResult")
    if result.quoteDanger:
        raise error(result, ERROR_QUOTE_DANGER)
    if result.isInStr:
        raise error(result, ERROR_UNCLOSED_QUOTE)

    if len(result.parenStack) != 0:
        if result.mode == PAREN_MODE:
          raise error(result, ERROR_UNCLOSED_PAREN)

    if result.mode == INDENT_MODE:
        initLine(result)
        onIndent(result)

    result.success = True

def processError(result, e):
    p("processError")
    result.success = False
    if 'parinferError' in e:
        del e['parinferError']
        result.error = e
    else:
        result.error.name = ERROR_UNHANDLED
        result.error.message = e.stack
        raise e

def processText(text, options, mode, smart=False):
    p("processText")
    result = getInitialResult(text, options, mode, smart)
    p(result)
    try:
        for i in range(len(result.inputLines)):
            result.inputLineNo = i
            processLine(result, i)
        finalizeResult(result)
    except ParinferError as e:
        errorDetails = e.args[0]
        if 'leadingCloseParen' in errorDetails or 'releaseCursorHold' in errorDetails:
            assert mode != PAREN_MODE
            p("re-processText")
            return processText(text, options, PAREN_MODE, smart)
        processError(result, errorDetails)

    return result

#-------------------------------------------------------------------------------
# Public API
#-------------------------------------------------------------------------------

def publicResult(result):
    p("publicResult")
    lineEnding = getLineEnding(result.origText)
    if result.success:
        final = {
            'text': lineEnding.join(result.lines),
            'cursorX': result.cursorX,
            'cursorLine': result.cursorLine,
            'success': True,
            'tabStops': result.tabStops,
            'parenTrails': result.parenTrails
        }
        if result.returnParens:
            final.parens = result.parens
    else:
        final = {
            'text': lineEnding.join(result.lines) if result.partialResult else result.origText,
            'cursorX': result.cursorX if result.partialResult else result.origCursorX,
            'cursorLine': result.cursorLine if result.partialResult else result.origCursorLine,
            'parenTrails': result.parenTrails if result.partialResult else None,
            'success': False,
            'error': result.error
        }
        if result.partialResult and result.returnParens:
            final.parens = result.parens

    if final['cursorX'] == UINT_NULL:
        del final['cursorX']
    if final['cursorLine'] == UINT_NULL:
        del final['cursorLine']
    if 'tabStops' in final and len(final['tabStops']) == 0:
        del final['tabStops']
    return final

def indent_mode(text, options):
    p("indent_mode")
    p("indent_mode on:",text)
    return publicResult(processText(text, options, INDENT_MODE))

def paren_mode(text, options):
    p("paren_mode")
    p("paren_mode on:",text)
    return publicResult(processText(text, options, PAREN_MODE))

def smart_mode(text, options):
    p("smart_mode")
    smart = False
    if isinstance(options, dict):
        smart = 'selectionStartLine' not in options or options['selectionStartLine'] is None
    return publicResult(processText(text, options, INDENT_MODE, smart))

API = {
    'version': '3.12.0',
    'indent_mode': indent_mode,
    'paren_mode': paren_mode,
    'smart_mode': smart_mode
}
