# type: ignore  # noqa: PGH003

"""Discord argument parsing library.

This module is a patch of the original argparse module, modifications being:
    - Explicit arguments are ignored. For example, this would not pass with argparse::

        parser = argparse.ArgumentParser()
        parser.add_argument("-d", "--debug", action="store_true")
        parser.parse_args("-dvalue".split())

    - Argument parsing is asynchronous, allowing discord.py converters to be used.
    - Does not exit on error, instead raises an exception.
"""

import contextlib
import sys
from argparse import (
    _UNRECOGNIZED_ARGS_ATTR,
    OPTIONAL,
    PARSER,
    REMAINDER,
    SUPPRESS,
    ZERO_OR_MORE,
    ArgumentError,
    ArgumentParser,
    ArgumentTypeError,
    Namespace,
    _get_action_name,
)
from gettext import gettext as _
from inspect import iscoroutinefunction

from discord.ext.commands import BadArgument


class DiscordArguments(ArgumentParser):
    async def parse_args(self, args=None, namespace=None):
        args, argv = await self.parse_known_args(args, namespace)
        if argv:
            msg = _("unrecognized arguments: %s")
            self.error(msg % " ".join(argv))
        return args

    async def parse_known_args(self, args=None, namespace=None):
        args = sys.argv[1:] if args is None else args

        # default Namespace built from parser defaults
        if namespace is None:
            namespace = Namespace()

        # add any action defaults that aren't present
        for action in self._actions:
            if (
                action.dest is not SUPPRESS
                and not hasattr(namespace, action.dest)
                and action.default is not SUPPRESS
            ):
                setattr(namespace, action.dest, action.default)

        # add any parser defaults that aren't present
        for dest in self._defaults:
            if not hasattr(namespace, dest):
                setattr(namespace, dest, self._defaults[dest])

        # parse the arguments and exit if there are any errors
        namespace, args = await self._parse_known_args(args, namespace)

        if hasattr(namespace, _UNRECOGNIZED_ARGS_ATTR):
            args.extend(getattr(namespace, _UNRECOGNIZED_ARGS_ATTR))
            delattr(namespace, _UNRECOGNIZED_ARGS_ATTR)
        return namespace, args

    async def _parse_known_args(self, arg_strings, namespace):
        # replace arg strings that are file references
        if self.fromfile_prefix_chars is not None:
            arg_strings = self._read_args_from_files(arg_strings)

        # map all mutually exclusive arguments to the other arguments
        # they can't occur with
        action_conflicts = {}
        for mutex_group in self._mutually_exclusive_groups:
            group_actions = mutex_group._group_actions
            for i, mutex_action in enumerate(mutex_group._group_actions):
                conflicts = action_conflicts.setdefault(mutex_action, [])
                conflicts.extend(group_actions[:i])
                conflicts.extend(group_actions[i + 1 :])

        # find all option indices, and determine the arg_string_pattern
        # which has an 'O' if there is an option at an index,
        # an 'A' if there is an argument, or a '-' if there is a '--'
        option_string_indices = {}
        arg_string_pattern_parts = []
        arg_strings_iter = iter(arg_strings)
        for i, arg_string in enumerate(arg_strings_iter):
            # all args after -- are non-options
            if arg_string == "--":
                arg_string_pattern_parts.append("-")
                arg_string_pattern_parts.extend("A" for _ in arg_strings_iter)
            # otherwise, add the arg to the arg strings
            # and note the index if it was an option
            else:
                option_tuple = self._parse_optional(arg_string)
                if option_tuple is None:
                    pattern = "A"
                else:
                    option_string_indices[i] = option_tuple
                    pattern = "O"
                arg_string_pattern_parts.append(pattern)

        # join the pieces together to form the pattern
        arg_strings_pattern = "".join(arg_string_pattern_parts)

        # converts arg strings to the appropriate and then takes the action
        seen_actions = set()
        seen_non_default_actions = set()

        async def take_action(action, argument_strings, option_string=None):
            seen_actions.add(action)
            argument_values = await self._get_values(action, argument_strings)

            # error if this argument is not allowed with other previously
            # seen arguments, assuming that actions that use the default
            # value don't really count as "present"
            if argument_values is not action.default:
                seen_non_default_actions.add(action)
                for conflict_action in action_conflicts.get(action, []):
                    if conflict_action in seen_non_default_actions:
                        msg = _("not allowed with argument %s")
                        action_name = _get_action_name(conflict_action)
                        raise ArgumentError(action, msg % action_name)

            # take the action if we didn't receive a SUPPRESS value
            # (e.g. from a default)
            if argument_values is not SUPPRESS:
                action(self, namespace, argument_values, option_string)

        # function to convert arg_strings into an optional action
        async def consume_optional(start_index):
            # get the optional identified at this index
            option_tuple = option_string_indices[start_index]
            action, option_string, explicit_arg, __ = option_tuple

            # identify additional optionals in the same arg string
            # (e.g. -xyz is the same as -x -y -z if no args are required)
            match_argument = self._match_argument
            action_tuples = []
            while True:
                # if we found no optional action, skip it
                if action is None:
                    extras.append(arg_strings[start_index])
                    return start_index + 1

                # if there is an explicit argument, try to match the
                # optional's string arguments to only this
                if explicit_arg is not None:
                    arg_count = match_argument(action, "A")

                    # if the action is a single-dash option and takes no
                    # arguments, try to parse more single-dash options out
                    # of the tail of the option string
                    chars = self.prefix_chars
                    if (
                        arg_count == 0
                        and option_string[1] not in chars
                        and explicit_arg != ""
                    ):
                        action_tuples.append((action, [], option_string))
                        char = option_string[0]
                        option_string = char + explicit_arg[0]
                        new_explicit_arg = explicit_arg[1:] or None
                        optionals_map = self._option_string_actions
                        if option_string in optionals_map:
                            action = optionals_map[option_string]
                            explicit_arg = new_explicit_arg
                        else:
                            # We are going to **actually** ignore explicit arguments here.
                            # This means we will not be able to parse arguments like `-dvalue`,
                            # but we're dealing with Discord text commands, and not the CLI.

                            # msg = _("ignored explicit argument %r")
                            # raise ArgumentError(action, msg % explicit_arg)
                            action = None
                            explicit_arg = None

                    # if the action expect exactly one argument, we've
                    # successfully matched the option; exit the loop
                    elif arg_count == 1:
                        stop = start_index + 1
                        args = [explicit_arg]
                        action_tuples.append((action, args, option_string))
                        break

                    # error if a double-dash option did not use the
                    # explicit argument
                    else:
                        msg = _("ignored explicit argument %r")
                        raise ArgumentError(action, msg % explicit_arg)

                # if there is no explicit argument, try to match the
                # optional's string arguments with the following strings
                # if successful, exit the loop
                else:
                    start = start_index + 1
                    selected_patterns = arg_strings_pattern[start:]
                    arg_count = match_argument(action, selected_patterns)
                    stop = start + arg_count
                    args = arg_strings[start:stop]
                    action_tuples.append((action, args, option_string))
                    break

            # add the Optional to the list and return the index at which
            # the Optional's string args stopped
            assert action_tuples
            for action, args, option_string in action_tuples:
                await take_action(action, args, option_string)
            return stop

        # the list of Positionals left to be parsed; this is modified
        # by consume_positionals()
        positionals = self._get_positional_actions()

        # function to convert arg_strings into positional actions
        async def consume_positionals(start_index) -> int:
            # match as many Positionals as possible
            match_partial = self._match_arguments_partial
            selected_pattern = arg_strings_pattern[start_index:]
            arg_counts = match_partial(positionals, selected_pattern)

            # slice off the appropriate arg strings for each Positional
            # and add the Positional and its args to the list
            for action, arg_count in zip(positionals, arg_counts):
                args = arg_strings[start_index : start_index + arg_count]
                start_index += arg_count
                await take_action(action, args)

            # slice off the Positionals that we just parsed and return the
            # index at which the Positionals' string args stopped
            positionals[:] = positionals[len(arg_counts) :]
            return start_index

        # consume Positionals and Optionals alternately, until we have
        # passed the last option string
        extras = []
        start_index = 0
        if option_string_indices:
            max_option_string_index = max(option_string_indices)
        else:
            max_option_string_index = -1
        while start_index <= max_option_string_index:  # type: ignore[reportGeneralTypeIssues]
            # consume any Positionals preceding the next option
            next_option_string_index = min(
                [index for index in option_string_indices if index >= start_index]
            )
            if start_index != next_option_string_index:
                positionals_end_index = await consume_positionals(start_index)

                # only try to parse the next optional if we didn't consume
                # the option string during the positionals parsing
                if positionals_end_index > start_index:
                    start_index = positionals_end_index
                    continue
                start_index = positionals_end_index

            # if we consumed all the positionals we could and we're not
            # at the index of an option string, there were extra arguments
            if start_index not in option_string_indices:
                strings = arg_strings[start_index:next_option_string_index]
                extras.extend(strings)
                start_index = next_option_string_index

            # consume the next optional and any arguments for it
            start_index = await consume_optional(start_index)

        # consume any positionals following the last Optional
        stop_index = await consume_positionals(start_index)

        # if we didn't consume all the argument strings, there were extras
        extras.extend(arg_strings[stop_index:])

        # make sure all required actions were present and also convert
        # action defaults which were not given as arguments
        required_actions = []
        for action in self._actions:
            if action not in seen_actions:
                if action.required:
                    required_actions.append(_get_action_name(action))
                else:
                    # Convert action default now instead of doing it before
                    # parsing arguments to avoid calling convert functions
                    # twice (which may fail) if the argument was given, but
                    # only if it was defined already in the namespace
                    if (
                        action.default is not None
                        and isinstance(action.default, str)
                        and hasattr(namespace, action.dest)
                        and action.default is getattr(namespace, action.dest)
                    ):
                        setattr(
                            namespace,
                            action.dest,
                            self._get_value(action, action.default),
                        )

        if required_actions:
            self.error(
                _("the following arguments are required: %s")
                % ", ".join(required_actions)
            )

        # make sure all required groups had one option present
        for group in self._mutually_exclusive_groups:
            if group.required:
                for action in group._group_actions:
                    if action in seen_non_default_actions:
                        break

                # if no actions were used, report the error
                else:
                    names = [
                        _get_action_name(action)
                        for action in group._group_actions
                        if action.help is not SUPPRESS
                    ]
                    msg = _("one of the arguments %s is required")
                    self.error(msg % " ".join(names))  # type: ignore[reportGeneralTypeIssues]

        # return the updated namespace and the extra arguments
        return namespace, extras

    async def parse_intermixed_args(self, args=None, namespace=None):
        args, argv = await self.parse_known_intermixed_args(args, namespace)
        if argv:
            msg = _("unrecognized arguments: %s")
            self.error(msg % " ".join(argv))
        return args

    async def parse_known_intermixed_args(self, args=None, namespace=None):
        # returns a namespace and list of extras
        #
        # positional can be freely intermixed with optionals.  optionals are
        # first parsed with all positional arguments deactivated.  The 'extras'
        # are then parsed.  If the parser definition is incompatible with the
        # intermixed assumptions (e.g. use of REMAINDER, subparsers) a
        # TypeError is raised.
        #
        # positionals are 'deactivated' by setting nargs and default to
        # SUPPRESS.  This blocks the addition of that positional to the
        # namespace

        positionals = self._get_positional_actions()
        a = [action for action in positionals if action.nargs in [PARSER, REMAINDER]]
        if a:
            raise TypeError(
                "parse_intermixed_args: positional arg with nargs=%s" % a[0].nargs
            )

        if [
            action.dest
            for group in self._mutually_exclusive_groups
            for action in group._group_actions
            if action in positionals
        ]:
            msg = "parse_intermixed_args: positional in mutuallyExclusiveGroup"
            raise TypeError(msg)

        try:
            save_usage = self.usage
            try:
                if self.usage is None:
                    # capture the full usage for use in error messages
                    self.usage = self.format_usage()[7:]
                for action in positionals:
                    # deactivate positionals
                    action.save_nargs = action.nargs  # type: ignore[reportGeneralTypeIssues]
                    # action.nargs = 0
                    action.nargs = SUPPRESS
                    action.save_default = action.default  # type: ignore[reportGeneralTypeIssues]
                    action.default = SUPPRESS
                namespace, remaining_args = await self.parse_known_args(args, namespace)
                for action in positionals:
                    # remove the empty positional values from namespace
                    if (
                        hasattr(namespace, action.dest)
                        and getattr(namespace, action.dest) == []
                    ):
                        from warnings import warn

                        warn(  # noqa: B028
                            "Do not expect %s in %s" % (action.dest, namespace)
                        )
                        delattr(namespace, action.dest)
            finally:
                # restore nargs and usage before exiting
                for action in positionals:
                    action.nargs = action.save_nargs  # type: ignore[reportGeneralTypeIssues]
                    action.default = action.save_default  # type: ignore[reportGeneralTypeIssues]
            optionals = self._get_optional_actions()
            try:
                # parse positionals.  optionals aren't normally required, but
                # they could be, so make sure they aren't.
                for action in optionals:
                    action.save_required = action.required  # type: ignore[reportGeneralTypeIssues]
                    action.required = False
                for group in self._mutually_exclusive_groups:
                    group.save_required = group.required  # type: ignore[reportGeneralTypeIssues]
                    group.required = False
                namespace, extras = await self.parse_known_args(
                    remaining_args, namespace
                )
            finally:
                # restore parser values before exiting
                for action in optionals:
                    action.required = action.save_required  # type: ignore[reportGeneralTypeIssues]
                for group in self._mutually_exclusive_groups:
                    group.required = group.save_required  # type: ignore[reportGeneralTypeIssues]
        finally:
            self.usage = save_usage  # type: ignore[reportUnboundVariable]
        return namespace, extras

    # ========================
    # Value conversion methods
    # ========================
    async def _get_values(self, action, arg_strings):
        # for everything but PARSER, REMAINDER args, strip out first '--'
        if action.nargs not in [PARSER, REMAINDER]:
            with contextlib.suppress(ValueError):
                arg_strings.remove("--")

        # optional argument produces a default when not present
        if not arg_strings and action.nargs == OPTIONAL:
            value = action.const if action.option_strings else action.default
            if isinstance(value, str):
                value = await self._get_value(action, value)
                self._check_value(action, value)

        # when nargs='*' on a positional, if there were no command-line
        # args, use the default if it is anything other than None
        elif (
            not arg_strings
            and action.nargs == ZERO_OR_MORE
            and not action.option_strings
        ):
            value = action.default if action.default is not None else arg_strings
            self._check_value(action, value)

        # single argument or optional argument produces a single value
        elif len(arg_strings) == 1 and action.nargs in [None, OPTIONAL]:
            (arg_string,) = arg_strings
            value = await self._get_value(action, arg_string)
            self._check_value(action, value)

        # REMAINDER arguments convert all values, checking none
        elif action.nargs == REMAINDER:
            value = [await self._get_value(action, v) for v in arg_strings]

        # PARSER arguments convert all values, but check only the first
        elif action.nargs == PARSER:
            value = [await self._get_value(action, v) for v in arg_strings]
            self._check_value(action, value[0])

        # SUPPRESS argument does not put anything in the namespace
        elif action.nargs == SUPPRESS:
            value = SUPPRESS

        # all other types of nargs produce a list
        else:
            value = [await self._get_value(action, v) for v in arg_strings]
            for v in value:
                self._check_value(action, v)

        # return the converted value
        return value

    async def _get_value(self, action, arg_string):
        type_func = self._registry_get("type", action.type, action.type)
        if not callable(type_func):
            msg = _("%r is not callable")
            raise ArgumentError(action, msg % type_func)

        # convert the value to the appropriate type
        try:
            if iscoroutinefunction(type_func):
                result = await type_func(arg_string)
            else:
                result = type_func(arg_string)

        # ArgumentTypeErrors indicate errors
        except ArgumentTypeError as err:
            name = getattr(action.type, "__name__", repr(action.type))
            msg = str(err)
            raise ArgumentError(action, msg) from None

        # TypeErrors or ValueErrors also indicate errors
        except (TypeError, ValueError):
            name = getattr(action.type, "__name__", repr(action.type))
            args = {"type": name, "value": arg_string}
            msg = _("invalid %(type)s value: %(value)r")
            raise ArgumentError(action, msg % args) from None

        # d.py converters
        except BadArgument as e:
            msg = str(e)
            raise ArgumentError(action, msg) from None

        # return the converted value
        return result
