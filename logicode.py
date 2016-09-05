import os
import re
import operator as op
import argparse
from random import randint

from lgc_grammar import *

if not hasattr(__builtins__, 'raw_input'):
    __builtins__.raw_input = input
if not hasattr(__builtins__, 'basestring'):
    __builtins__.basestring = str

rLinestart = re.compile("^", re.M)
rGetParentFunctionName = re.compile("<function ([^.]+)")

def getParentFunctionName(lambda_function):
    return rGetParentFunctionName.match(repr(lambda_function)).group(1)

def islambda(v):
  LAMBDA = lambda: 0
  return isinstance(v, type(LAMBDA)) and v.__name__ == LAMBDA.__name__

def Inject(scope, keys, values):
    for key, value in zip(keys, values):
        scope.lookup[key] = value
    return scope

rWhitespace = re.compile(r"[ \t]+", re.M)
rNewlines = re.compile(r"[\r\n]+", re.M)
rBits = re.compile(r"[01]+")
rName = re.compile(r"(?!\binput\b|\b__scope__\b)[a-zA-Z_$]+")
rRandom = re.compile(r"\?")
rInput = re.compile(r"\binput\b")
rScope = re.compile(r"\b__scope__\b")
rInfix = re.compile(r"[&|]")
rPrefix = re.compile(r"!")
rPostfix = re.compile(r"\[[ht]\]")
rOpenParenthesis = re.compile(r"\(")
rCloseParenthesis = re.compile(r"\)")
rCircuit = re.compile(r"\bcirc\b")
rVariable = re.compile(r"\bvar\b")
rCondition = re.compile(r"\bcond\b")
rOut = re.compile(r"out ")
rComment = re.compile(r"#.*")
rLambda = re.compile(r"->")
rOr = re.compile(r"/")
rComma = re.compile(r",")
rEquals = re.compile(r"=")
rPlus = re.compile(r"\+")

grammars = {
    "Newlines": [rNewlines],
    "Bits": [rBits],
    "Name": [rName],
    "Random": [rRandom],
    "Input": [rInput],
    "Scope": [rScope],
    "Literal": [["|", "Input", "Scope", "Bits", "Name", "Random"]],
    "Arguments": [
        rOpenParenthesis,
        ["?", rName, ["*", rComma, rName]],
        rCloseParenthesis
    ],
    "Call Arguments": [
        rOpenParenthesis,
        ["?", "Literal", ["*", rComma, "Literal"]],
        rCloseParenthesis
    ],
    "Alpha": [
        [
            "|",
            ["1", rPrefix, "Expression"],
            ["1", "Name", "Call Arguments"],
            ["1", rOpenParenthesis, "Expression", rCloseParenthesis],
            "Literal"
        ]
    ],
    "Expression": [
        [
            "|",
            ["1", "Alpha", rPlus, "Expression"],
            ["1", "Alpha", rInfix, "Expression"],
            ["1", rPrefix, "Expression"],
            ["1", "Alpha", rPostfix],
            ["1", "Name", "Call Arguments"],
            ["1", rOpenParenthesis, "Expression", rCloseParenthesis],
            "Literal"
        ]
    ],
    "Circuit": [rCircuit, rName, "Arguments", rLambda, "Expression"],
    "Variable": [rVariable, rName, rEquals, "Expression"],
    "Condition": [
        rCondition,
        "Expression",
        rLambda,
        ["|", "Variable", "Out"],
        rOr,
        ["|", "Variable", "Out"]
    ],
    "Out": [rOut, "Expression"],
    "Comment": [rComment],
    "Program": [
        [
            "+",
            ["|", "Circuit", "Variable", "Condition", "Out", "Comment", "Newlines", "Expression"]
        ]
    ]
}

transform = {
    "Newlines": GrammarParse.NoLambda,
    "Bits": GrammarParse.Bits,
    "Name": GrammarParse.Name,
    "Random": GrammarParse.Random,
    "Input": GrammarParse.Input,
    "Scope": GrammarParse.ScopeTransform,
    "Literal": GrammarParse.Literal,
    "Arguments": GrammarParse.Arguments,
    "Call Arguments": GrammarParse.Arguments,
    "Alpha": GrammarParse.Expression,
    "Expression": GrammarParse.Expression,
    "Circuit": GrammarParse.Circuit,
    "Variable": GrammarParse.Variable,
    "Condition": GrammarParse.Condition,
    "Out": GrammarParse.Out,
    "Comment": GrammarParse.NoLambda
}

mins = {
    "?": 0,
    "*": 0,
    "+": 1
}

maxes = {
    "?": 1,
    "*": -1,
    "+": -1
}


def Print(self, result):
    print("".join(list(map(str, result))))


def Transform(token, argument):
    return (transform.get(token, GrammarParse.Noop)(argument[0]), argument[1])


def NoTransform(token, argument):
    return argument


def Get(code, token, process=Transform):
    length = 0
    match = rWhitespace.match(code)
    if match:
        string = match.group()
        length += len(string)
        code = code[length:]
    if isinstance(token, list):
        first = token[0]
        rest = token[1:]
        if first == "|":
            for token in rest:
                result = Get(code, token, process)
                if result[0] != None:
                    return (result[0], result[1] + length)
            return (None, 0)
        minN = int(mins.get(first, first))
        maxN = int(maxes.get(first, first))
        result = []
        amount = 0
        while amount != maxN:
            tokens = []
            success = True
            for token in rest:
                gotten = Get(code, token, process)
                if gotten[0] == None:
                    success = False
                    break
                tokens += [gotten[0]]
                gottenLength = gotten[1]
                code = code[gottenLength:]
                length += gottenLength
            if not success:
                break
            result += [tokens]
            amount += 1
        if amount < minN:
            return (None, 0)
        return (result, length)
    if isinstance(token, basestring):
        result = []
        grammar = grammars[token]
        for tok in grammar:
            gotten = Get(code, tok, process)
            if gotten[0] == None:
                return (None, 0)
            result += [gotten[0]]
            gottenLength = gotten[1]
            code = code[gottenLength:]
            length += gottenLength
        return process(token, (result, length))
    if isinstance(token, re._pattern_type):
        match = token.match(code)
        if match:
            string = match.group()
            return (string, len(string) + length)
        return (None, 0)


def run(code="", input="", astify_var=False, grammar="Program", repl=False, scope=None):
    if not scope:
        scope = Scope()
    if repl:
        while repl:
            try:
                Print(run(raw_input("Logicode> "), scope=scope))
            except (KeyboardInterrupt, EOFError):
                return
    scope["input"] = list(map(int, filter(
        lambda c: c == "0" or c == "1",
        input
    )))[::-1]
    if astify_var:
        result = Get(code, grammar, NoTransform)[0]
        print(Astify(result))
        return
    result = Get(code, grammar)[0]
    if result:
        program = result[0]
        for statement in program:
            result = statement[0](scope)
        return result


def Astify(parsed, padding=""):
    result = ""
    if isinstance(parsed, list):
        padding += " "
        for part in parsed:
            result += Astify(part, padding)
        return result
    else:
        return padding + str(parsed) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("-f", "--file", type=str, nargs="*", default="",
                        help="File path of the program.")
    parser.add_argument("-c", "--code", type=str, nargs="?", default="",
                        help="Code of the program.")
    parser.add_argument("-i", "--input", type=str, nargs="?", default="",
                        help="Input to the program.")
    parser.add_argument("-a", "--astify", action="store_true",
                        help="Print AST instead of interpreting.")
    parser.add_argument("-r", "--repl", action="store_true",
                        help="Open as REPL instead of interpreting.")
    argv = parser.parse_args()
    if argv.repl:
        run(repl=True)
    elif len(argv.file):
        code = ""
        for path in argv.file:
            if os.path.isfile(argv.file[0]):
                with open(argv.file[0]) as file:
                    code += file.read() + "\n"
            else:
                with open(argv.file[0] + ".lgc") as file:
                    code += file.read() + "\n"
        if argv.astify:
            run(code, "", True)
        elif argv.input:
            run(code, argv.input)
        else:
            run(code)
    elif argv.code:
        if argv.astify:
            run(argv.code, "", True)
        elif argv.input:
            run(argv.code, argv.input)
        else:
            run(argv.code)
    else:
        code = raw_input("Enter program: ")
        if argv.astify:
            run(code, "", True)
        elif argv.input:
            run(code, argv.input[0])
        else:
            run(code)
