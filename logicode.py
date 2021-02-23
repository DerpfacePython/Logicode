import os
import re
import operator as op
import argparse
import sys
from random import randint

sys.setrecursionlimit(15000)

if not hasattr(__builtins__, "raw_input"):
    raw_input = input
if not hasattr(__builtins__, "basestring"):
    basestring = str

if hasattr(re, "Pattern"):
    regex = re.Pattern
else:
    regex = re._pattern_type

rWhitespace = re.compile(r"[ \t]+", re.M)
rCommandSeparator = re.compile(r"[\r\n;]+", re.M)
rBits = re.compile(r"[01]+")
rName = re.compile(r"(?!\b[ab]inp\b|\b__scope__\b)[a-zA-Z0-9_$]+")
rRandom = re.compile(r"\?")
rInput = re.compile(r"\b[ab]inp\b")
rScope = re.compile(r"\b__scope__\b")
rInfix = re.compile(r"[&|]")
rPrefix = re.compile(r"[!~@\*]")
rPostfix = re.compile(r"[<>]")
rOpenParenthesis = re.compile(r"\(")
rCloseParenthesis = re.compile(r"\)")
rOpenBracket = re.compile(r"\[")
rCloseBracket = re.compile(r"\]")
rMultilineCond = re.compile(r"\]/\[")
rCircuit = re.compile(r"\bcirc\b")
rVariable = re.compile(r"\bvar\b")
rCondition = re.compile(r"\bcond\b")
rOut = re.compile(r"\bout\b")
rComment = re.compile(r"#.*")
rLambda = re.compile(r"->")
rOr = re.compile(r"/")
rComma = re.compile(r",")
rEquals = re.compile(r"=")
rPlus = re.compile(r"\+")

rLinestart = re.compile("^", re.M)
rGetParentFunctionName = re.compile("<function ([^.]+)")

# Utility functions

def And(left, right):
    length = max(len(left), len(right))
    return list(map(op.and_, [0] * (length - len(left)) + left, [0] * (length - len(right)) + right))

def Or(left, right):
    length = max(len(left), len(right))
    return list(map(op.or_, [0] * (length - len(left)) + left, [0] * (length - len(right)) + right))

# Parser functions

def Noop(argument):
    return argument


def NoLambda(result):
    return lambda scope: None


def Bits(result):
    value = list(map(lambda char: int(char), result[0]))
    return lambda scope: value


def Name(result):
    return lambda scope: scope[result[0]]


def Random(result):
    return lambda scope: [randint(0, 1)]


def Input(result):
    return lambda scope: GetInput(scope, result[0][0])


def ScopeTransform(result):
    return lambda scope: Print(repr(scope))


def Literal(result):
    return [result]


def Arguments(result):
    arguments = result[1]
    if len(arguments):
        arguments = arguments[0]
        if (isinstance(arguments, list) and isinstance(arguments[-1], list) and len(arguments[-1])
               and len(arguments[-1][0]) == 2):
            arguments = arguments[:-1] + list(map(lambda l: l[1], arguments[1]))
    if len(arguments) and isinstance(arguments[-1], list) and not len(arguments[-1]):
        arguments = arguments[:-1]
    return lambda scope: arguments


def Expression(result):
    length = len(result)
    if length == 1 and hasattr(result[0], "__call__"):
        result = result[0]
        while isinstance(result, list) and len(result) == 1:
            result = result[0]
        return result
    result = result[0][0]
    length = len(result)
    if length == 3:
        if (isinstance(result[0], basestring) and rOpenParenthesis.match(result[0])):
            return result[1]
        operator = result[1]
        if isinstance(operator, basestring) and rPlus.match(operator):
            return lambda scope: result[0](scope) + result[2](scope)
        if isinstance(operator, basestring) and rInfix.match(operator):
            if operator == "&":
                return lambda scope: And(result[0](scope), result[2](scope))
            if operator == "|":
                return lambda scope: Or(result[0](scope), result[2](scope))
    if length == 2:
        operator = result[0]
        if isinstance(operator, basestring) and rPrefix.match(operator):
            if operator == "!":
                return lambda scope: list(map(int, map(op.not_, result[1](scope))))
            if operator == "~":
                return lambda scope: list(result[1](scope)[::-1])
            if operator == "@":
                return lambda scope: list(chr(int("".join(str(x) for x in result[1](scope)), 2) % 256))
            if operator == "*":
                return lambda scope: [1] if 1 in result[1](scope) else [0]
        if isinstance(result[1], list):
            operators = result[1]
            start_index = 0
            head = False
            for wrapped_operator in operators:
                operator = wrapped_operator[0]
                if operator == "<":
                    head = True
                    break
                if operator == ">":
                    start_index += 1
            if head:
                return lambda scope: [result[0](scope)[start_index]]
            return lambda scope: result[0](scope)[start_index:]
        # Function call
        name = result[0]
        args = result[1]
        return lambda scope: name(scope)(list(map(lambda arg: arg(scope), args(scope))))
    if length == 1:
        return result[0]


def Circuit(result):
    name = result[1]
    arguments = result[2]
    body = result[4]
    if isinstance(body, list):
        expressions = map(lambda l: l[0], body[0][1])
        body = lambda scope: list(filter(None, map(lambda expression: expression(scope), expressions)))[-1]
    return lambda scope: scope.set(name, lambda args: body(Inject(Scope(scope), arguments(scope), args)))


def Variable(result):
    length = len(result[2])
    name = result[1]
    if length:
        value = result[2][0][1]
    else:
        value = lambda n: [0]
    return lambda scope: scope.set(name, value(scope))


def Condition(result):
    condition = result[1]
    body = result[3][0]
    if isinstance(body[1], list):
        expressions_true = map(lambda l: l[0], body[1])
        expressions_false = map(lambda l: l[0], body[3])
        if_true = lambda scope: ([None] + list(filter(None, map(lambda expression: expression(scope), expressions_true))))[-1]
        if_false = lambda scope: ([None] + list(filter(None, map(lambda expression: expression(scope), expressions_false))))[-1]
    else:
        if_true = body[0]
        if_false = body[2]
    return lambda scope: if_true(scope) if 1 in condition(scope) else if_false(scope)


def Out(result):
    return lambda scope: Print(result[1](scope))


def GetInput(scope, inputarg):
    if not len(scope["input"]):
        if inputarg == "a":
            temp = list(x for x in raw_input("Input: ") if ord(x) < 256)
            for a in range(len(temp)):
                temp[a] = bin(ord(temp[a]))[2:]
                while len(temp[a]) < 8:
                    temp[a] = "0" + temp[a]
            temp = "".join(temp)
            scope["input"] = [[int(x) for x in temp]]
        if inputarg == "b":
            scope["input"] = [list(map(int, filter(lambda c: c == "0" or c == "1", raw_input("Input: "))))]
    return scope["input"].pop()


def Print(result):
    if result:
        print("".join(list(map(str, result))))


# Scope stuff

def getParentFunctionName(lambda_function):
    return rGetParentFunctionName.match(repr(lambda_function)).group(1)


def islambda(v):
  LAMBDA = lambda: 0
  return isinstance(v, type(LAMBDA)) and v.__name__ == LAMBDA.__name__


class Scope:
    def __init__(self, parent={}):
        self.parent = parent
        self.lookup = {}

    def __contains__(self, key):
        return key in self.parent or key in self.lookup

    def __getitem__(self, key):
        if key in self.lookup:
            return self.lookup[key]
        else:
            return self.parent[key]

    def __setitem__(self, key, value):
        if key in self.lookup:
            self.lookup[key] = value
        elif key in self.parent:
            self.parent[key] = value
        else:
            self.lookup[key] = value

    def __delitem__(self, key):
        if key in self.lookup:
            del self.lookup[key]
        else:
            del self.parent[key]

    def __repr__(self):
        string = "{"
        for key in self.lookup:
            value = self.lookup[key]
            string += "%s: %s" % (key,
                (getParentFunctionName(value) if islambda(value) else "".join(list(map(str, value)))
                 if isinstance(value, list) else repr(value)))
            string += ", "
        string = string[:-2] + "}"
        if string == "}":
            string = "{}"
        return (string +
            "\n" +
            rLinestart.sub("    ", repr(self.parent)))

    def has(self, key):
        return key in self

    def get(self, key):
        return self[key]

    def set(self, key, value):
        self[key] = value

    def delete(self, key):
        del self[key]


# Dictionaries:

# Grammars
grammars = {
    "CommandSeparator": [rCommandSeparator],
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
        ["?", "TopLevelExpression", ["*", rComma, "TopLevelExpression"]],
        rCloseParenthesis
    ],
    "Term": [
        [
            "|",
            ["1", rOpenParenthesis, "TopLevelExpression", rCloseParenthesis],
            "Literal"
        ]
    ],
    "Alpha": [
        [
            "|",
            ["1", rPrefix, "Term"],
            ["1", "Name", "Call Arguments"],
            ["1", rOpenParenthesis, "TopLevelExpression", rCloseParenthesis],
            "Literal"
        ]
    ],
    "Expression": [
        [
            "|",
            ["1", "Alpha", rInfix, "Expression"],
            ["1", rPrefix, "Term"],
            ["1", "Alpha", ["+", rPostfix]],
            ["1", "Name", "Call Arguments"],
            ["1", rOpenParenthesis, "TopLevelExpression", rCloseParenthesis],
            "Literal"
        ]
    ],
    "TopLevelExpression": [
        [
            "|",
            ["1", "Expression", rPlus, "TopLevelExpression"],
            ["1", "Expression"]
        ]
    ],
    "Circuit": [
        rCircuit,
        rName,
        "Arguments",
        rLambda,
        [
            "|",
            "Condition",
            "TopLevelExpression",
            "Variable",
            "Out",
            [
                "1", rOpenBracket,
                ["+", ["|", "CommandSeparator", "Condition", "Variable", "TopLevelExpression", "Out"]],
                rCloseBracket
            ]
        ]
    ],
    "Variable": [
        rVariable, rName,
        ["?", rEquals, "TopLevelExpression"]
    ],
    "Condition": [
        rCondition,
        "TopLevelExpression",
        rLambda,
        [
            "|",
            [
                "1",
                ["|", "Variable", "Out", "TopLevelExpression"],
                rOr,
                ["|", "Variable", "Out", "TopLevelExpression"]
            ], [
                "1", rOpenBracket,
                ["+", ["|", "CommandSeparator", "Variable", "Out", "TopLevelExpression"]],
                rMultilineCond,
                ["+", ["|", "CommandSeparator", "Variable", "Out", "TopLevelExpression"]],
                rCloseBracket
            ]
        ]
    ],
    "Out": [rOut, "TopLevelExpression"],
    "Comment": [rComment],
    "Program": [
        [
            "+",
            ["|", "CommandSeparator", "Comment", "Circuit", "Variable", "Condition", "Out", "TopLevelExpression"]
        ]
    ]
}

# Transforming grammars to functions
transform = {
    "CommandSeparator": NoLambda,
    "Bits": Bits,
    "Name": Name,
    "Random": Random,
    "Input": Input,
    "Scope": ScopeTransform,
    "Literal": Literal,
    "Arguments": Arguments,
    "Call Arguments": Arguments,
    "Term": Expression,
    "Alpha": Expression,
    "Expression": Expression,
    "TopLevelExpression": Expression,
    "Circuit": Circuit,
    "Variable": Variable,
    "Condition": Condition,
    "Out": Out,
    "Comment": NoLambda
}

# Mins and maxes
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


def Inject(scope, keys, values):
    for key, value in zip(keys, values):
        scope.lookup[key] = value
    return scope


def Transform(token, argument):
    return (transform.get(token, Noop)(argument[0]), argument[1])


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

    if isinstance(token, regex):
        match = token.match(code)
        if match:
            string = match.group()
            return (string, len(string) + length)
        return (None, 0)


def Run(code="", input="", astify=False, grammar="Program", repl=False, scope=None):
    if not scope:
        scope = Scope()
    if repl:
        while repl:
            try:
                Print(Run(raw_input("Logicode> "), scope=scope))
            except (KeyboardInterrupt, EOFError):
                return
    scope["input"] = list(map(lambda i: list(map(int, filter(lambda c: c == "0" or c == "1", i))),
                          filter(None, input.split("\n")[::-1])))
    if astify:
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
    parser.add_argument("-f", "--file", type=str, nargs="*", default="", help="File path of the program.")
    parser.add_argument("-c", "--code", type=str, nargs="?", default="", help="Code of the program.")
    parser.add_argument("-i", "--input", type=str, nargs="?", default="", help="Input to the program.")
    parser.add_argument("-a", "--astify", action="store_true", help="Print AST instead of interpreting.")
    parser.add_argument("-r", "--repl", action="store_true", help="Open as REPL instead of interpreting.")
    parser.add_argument("-t", "--test", action="store_true", help="Run unit tests.")
    argv = parser.parse_args()
    if argv.test:
        from test import *
        RunTests()
    elif argv.repl:
        Run(repl=True)
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
            Run(code, "", True)
        elif argv.input:
            Run(code, argv.input)
        else:
            Run(code)
    elif argv.code:
        if argv.astify:
            Run(argv.code, "", True)
        elif argv.input:
            Run(argv.code, argv.input)
        else:
            Run(argv.code)
    else:
        code = raw_input("Enter program: ")
        if argv.astify:
            Run(code, "", True)
        elif argv.input:
            Run(code, argv.input[0])
        else:
            Run(code)
