"""Bounded, side-effect-free simulation of config aliases and key events.

This models config control flow, not the game or an anti-cheat verdict. It
never executes console commands, loads files, sends input, or touches disk.
"""
from __future__ import annotations

from . import cfglang

MAX_COMMANDS = 512
MAX_EVENTS = 24


class Simulation:
    def __init__(self, lines, entry, *, scan=None, target="", target_before=""):
        self.aliases = {}
        if scan is not None:
            for name in scan.aliases:
                item = scan.effective_alias(name)
                if item is not None:
                    self.aliases[name.lower()] = item.body
        for line in lines:
            for cmd in cfglang.parse_command_string(line):
                if cmd.lname == 'alias' and len(cmd.args) >= 2:
                    self.aliases[cmd.arg_text(0).lower()] = cmd.arg_text(1)
        self.bindings = {'script': entry}
        self.target = target.lower()
        if self.target:
            self.bindings[self.target] = target_before
        self.held = set()
        self.settings = {}
        self.trace = []
        self.errors = []
        self.warnings = []
        self.count = 0
        self.event = ''
        self.actions = set()

    def execute(self, body, stack=()):
        from .scriptgen import MOVE_ACTIONS

        for cmd in cfglang.parse_command_string(body):
            self.count += 1
            if self.count > MAX_COMMANDS:
                self.errors.append('Script expansion exceeded the simulation limit; simplify its alias chain.')
                return
            name = cmd.lname
            args = [a.text for a in cmd.args]
            text = body[cmd.start:cmd.end]
            if name in self.aliases:
                value = self.aliases[name]
                marker = (name, value)
                if marker in stack or len(stack) >= 32:
                    self.errors.append(f'Recursive alias: {name} calls an active alias without terminating.')
                    return
                self.trace.append({'event': self.event, 'command': name, 'kind': 'alias', 'depth': len(stack)})
                self.execute(value, stack + (marker,))
                if self.errors:
                    return
            elif name == 'alias' and len(args) >= 2:
                self.aliases[args[0].lower()] = args[1]
            elif name == 'bind' and len(args) >= 2:
                self.bindings[args[0].lower()] = args[1]
            elif name == 'unbind' and args:
                self.bindings[args[0].lower()] = ''
            elif name.startswith(('+', '-')):
                action = name[1:]
                if name.startswith('+'):
                    self.held.add(action)
                else:
                    self.held.discard(action)
                if action in MOVE_ACTIONS:
                    self.actions.add(action)
            elif name in ('exec', 'execifexists'):
                self.warnings.append('External config files are not executed in this simulation.')
            elif len(args) == 1 and name not in ('echo', 'say', 'say_team', 'use', 'buy', 'play'):
                self.settings[name] = args[0]
            self.trace.append({'event': self.event, 'command': text, 'kind': 'command',
                               'depth': len(stack), 'held': sorted(self.held),
                               'settings': dict(self.settings)})

    def feed(self, events):
        snapshots = []
        for event in events[:MAX_EVENTS]:
            if event not in ('down', 'up', 'target_down', 'target_up'):
                raise ValueError('Unknown simulation key event.')
            self.event = event
            self.actions = set()
            key = self.target if event.startswith('target_') else 'script'
            body = self.bindings.get(key, '')
            if event.endswith('up') or event == 'up':
                body = '-' + body[1:] if body.startswith('+') else ''
            self.execute(body)
            if len(self.actions) > 1:
                self.errors.append('One key event expands to multiple restricted inputs: ' + ', '.join(sorted(self.actions)) + '.')
            snapshots.append({'event': event, 'held': sorted(self.held),
                              'settings': dict(self.settings), 'bindings': dict(self.bindings)})
            if self.errors:
                break
        return {'trace': self.trace, 'events': snapshots, 'held': sorted(self.held),
                'settings': self.settings, 'bindings': self.bindings,
                'errors': list(dict.fromkeys(self.errors)),
                'warnings': list(dict.fromkeys(self.warnings)),
                'limits': 'Config simulation only. Game command availability, server rules and anti-cheat policies are not certified.'}


def simulate(lines, entry, *, scan=None, events=None, mode='press', target='', target_before=''):
    if events is None:
        events = ['down', 'up']
        if mode == 'toggle':
            events += ['down', 'up']
        elif mode == 'shift' and target:
            events = ['down', 'target_down', 'target_up', 'up', 'down', 'up']
    engine = Simulation(lines, entry, scan=scan, target=target, target_before=target_before)
    return engine.feed(list(events))


def validation(lines, entry, *, scan=None, mode='press', target=''):
    result = simulate(lines, entry, scan=scan, mode=mode, target=target)
    errors = list(result['errors'])
    if result['held']:
        errors.append('No reachable release for: ' + ', '.join('+' + x for x in result['held']) + '. These actions would remain held after the key sequence.')
    return list(dict.fromkeys(errors))
