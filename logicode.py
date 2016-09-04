import os
import re
import operator as op
import argparse
from random import randint

if not hasattr(__builtins__, 'raw_input'):
    __builtins__.raw_input = input
if not hasattr(__builtins__, 'basestring'):
    __builtins__.basestring = str


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

    def has(self, key):
        return key in self

    def get(self, key):
        return self[key]

    def set(self, key, value):
        self[key] = value

    def delete(self, key):
        del self[key]


def Inject(scope, keys, values):
    for key, value in zip(keys, values):
        scope.lookup[key] = value
    return scope


rWhitespace = re.compile(r"[ \t]+", re.M)
rNewlines = re.compile(r"[\r\n]+", re.M)
rName = re.compile(r"[A-Z_$]+", re.I)
rBit = re.compile(r"[01]")
rBits = re.compile(r"[01]+")
rInfix = re.compile(r"[&|]")
rPrefix = re.compile(r"!")
rPostfix = re.compile(r"\[[ht]\]")
rOpenParenthesis = re.compile(r"\(")
rCloseParenthesis = re.compile(r"\)")
rCircuit = re.compile(r"circ ")
rVariable = re.compile(r"var ")
rCondition = re.compile(r"cond ")
rOut = re.compile(r"out ")
rInput = re.compile(r"input")
rComment = re.compile(r"#.+")
rLambda = re.compile(r"->")
rOr = re.compile(r"/")
rComma = re.compile(r",")
rEquals = re.compile(r"=")
rPlus = re.compile(r"\+")
rRandom = re.compile(r"\?")

grammars = {
    "Bit": [rBit],
    "Bits": [rBits],
    "Name": [rName],
    "Random": [rRandom],
    "Input": [rInput],
    "Literal": [["|", "Bits", "Name", "Random", "Input"]],
    "Arguments": [rOpenParenthesis, ["?", rName, ["*", rComma, rName]], rCloseParenthesis],
    "Call Arguments": [rOpenParenthesis, ["?", "Literal", ["*", rComma, "Literal"]], rCloseParenthesis],
    "Alpha": [["|", ["1", rPrefix, "Expression"], ["1", "Name", "Arguments"],
               ["1", rOpenParenthesis, "Expression", rCloseParenthesis], "Literal"]],
    "Expression": [
        ["|", ["1", "Alpha", rPlus, "Expression"], ["1", "Alpha", rInfix, "Expression"], ["1", rPrefix, "Expression"],
         ["1", "Alpha", rPostfix], ["1", "Name", "Call Arguments"],
         ["1", rOpenParenthesis, "Expression", rCloseParenthesis], "Literal"]],
    "Circuit": [rCircuit, rName, "Arguments", rLambda, "Expression"],
    "Variable": [rVariable, rName, rEquals, "Expression"],
    "Out": [rOut, "Expression"],
    "Condition": [rCondition, rName, rLambda, [["Variable"], ["Out"]], rOr, [["Variable"], ["Out"]]],
    "Comment": [rComment],
    "Program": [["+", ["|", "Circuit", "Variable", "Condition", "Out", "Comment", rNewlines]]]
}


def Noop(argument):
    return argument


def Bits(result):
    value = list(map(lambda char: int(char), result[0]))
    return lambda scope: value


def Name(result):
    return lambda scope: scope[result[0]]


def Input(result):
    return lambda scope: [raw_input(">>> ")]


def Literal(result):
    return [result]


def Random(result):
    return lambda scope: [randint(0, 1)]


def Arguments(result):
    arguments = result[1]
    if len(arguments):
        arguments = arguments[0]
        while isinstance(arguments, list) and isinstance(arguments[-1], list) and len(arguments[-1][0]) == 2:
            last = arguments[-1]
            arguments = arguments[:-1] + [last[0][1]]
    return lambda scope: arguments


def Expression(result):
    if len(result) == 1 and hasattr(result[0], "__call__"):
        result = result[0]
        while isinstance(result, list) and len(result) == 1:
            result = result[0]
        return result
    result = result[0][0]
    if len(result) == 3:
        if isinstance(result[0], basestring) and rOpenParenthesis.match(result[0]):
            return result[1]
        operator = result[1]
        if isinstance(operator, basestring) and rPlus.match(operator):
            return lambda scope: result[0](scope) + result[2](scope)
        if isinstance(operator, basestring) and rInfix.match(operator):
            if operator == "&":
                return lambda scope: list(map(op.and_, result[0](scope), result[2](scope)))
            if operator == "|":
                return lambda scope: list(map(op.or_, result[0](scope), result[2](scope)))
    if len(result) == 2:
        operator = result[0]
        if isinstance(operator, basestring) and rPrefix.match(operator):
            if operator == "!":
                return lambda scope: list(map(int, map(op.not_, result[1](scope))))
        operator = result[1]
        if isinstance(operator, basestring) and rPostfix.match(operator):
            if operator == "[h]":
                return lambda scope: [result[0](scope)[0]]
            if operator == "[t]":
                return lambda scope: [result[0](scope)[-1]]
        # Function call
        name = result[0]
        args = result[1]
        return lambda scope: name(scope)(list(map(lambda arg: arg[0][0](scope), args(scope))))
    if len(result) == 1:
        return result[0]


def Circuit(result):
    name = result[1]
    arguments = result[2]
    expression = result[4]
    return lambda scope: scope.set(name, lambda args: expression(Inject(Scope(scope), arguments(scope), args)))


def Variable(result):
    name = result[1]
    value = result[3]
    return lambda scope: scope.set(name, value(scope))


def Condition(result):
    if_true = result[3]
    if_false = result[5]
    return lambda scope: lambda condition: if_true(scope) if condition else if_false(scope)


def Out(result):
    return lambda scope: Print(result[1](scope))


def Print(result):
    print("".join(list(map(str, result))))


transform = {
    "Bits": Bits,
    "Name": Name,
    "Input": Input,
    "Literal": Literal,
    "Random": Random,
    "Arguments": Arguments,
    "Call Arguments": Arguments,
    "Alpha": Expression,
    "Expression": Expression,
    "Circuit": Circuit,
    "Variable": Variable,
    "Condition": Condition,
    "Out": Out
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


def get(code, token):
    length = 0
    # jump whitespace
    match = rWhitespace.match(code)
    if match:
        string = match.group()
        length = len(string)
        code = code[length:]
    if isinstance(token, list):
        first = token[0]
        rest = token[1:]
        if first == "|":
            for token in rest:
                result = get(code, token)
                if result[0] != None:
                    return result
            return None, 0
        minN = int(mins.get(first, first))
        maxN = int(maxes.get(first, first))
        result = []
        amount = 0
        while amount != maxN:
            tokens = []
            success = True
            for token in rest:
                gotten = get(code, token)
                if gotten[0] == None:
                    success = False
                    break
                tokens += [gotten[0]]
                code = code[gotten[1]:]
                length += gotten[1]
            if not success:
                break
            result += [tokens]
            amount += 1
        if amount < minN:
            return None, 0
        return result, length
    if isinstance(token, basestring):
        result = []
        grammar = grammars[token]
        for tok in grammar:
            gotten = get(code, tok)
            if gotten[0] == None:
                return (None, 0)
            result += [gotten[0]]
            code = code[gotten[1]:]
            length += gotten[1]
        return (transform.get(token, Noop)(result), length)
    if isinstance(token, re._pattern_type):
        match = token.match(code)
        if match:
            string = match.group()
            return string, len(string)
        return None, 0


def run(code, grammar="Program"):
    scope = Scope()
    result = get(code, "Program")[0]
    if result:
        program = result[0]
        for statement in program:
            function = statement[0]
            if hasattr(function, '__call__'):
                function(scope)


def astify(parsed, padding=""):
    result = ""
    if isinstance(parsed, list):
        padding += " "
        for part in parsed:
            result += astify(part, padding)
        return result
    else:
        return padding + str(parsed) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument("-f", "--file", type=str, nargs='*', default="",
                        help="File path of the program.")
    argv = parser.parse_args()
    if len(argv.file):
        if os.path.isfile(argv.file[0]):
            with open(argv.file[0]) as file:
                code = file.read()
        else:
            with open(argv.file[0] + ".lgc") as file:
                code = file.read()
        run(code)
    else:
        run(raw_input("Enter program: "))
