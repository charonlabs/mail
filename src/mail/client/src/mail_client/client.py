# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import json
import shlex
from argparse import ArgumentParser, Namespace
from urllib.parse import urlsplit

from rich import print as rprint
from rich.console import Console
from rich.prompt import Prompt

from .api import MAILClient


class Newman:
    """
    NEWMAN: A CLI-based REPL client for the MAIL protocol.
    """
    def __init__(
        self,
        url: str,
    ) -> None:
        self.url = url
        self._api_key = None
        self._user_id = None
        self._user_role = None

        self._client = MAILClient(self.url, self._api_key)

        self._console = Console()
        self._parser = self._build_parser()

    def run_repl(self) -> None:
        """
        Run the REPL.
        """
        self._print_preamble()
        while True:
            prompt = self._repl_prompt()
            raw_input = self._console.input(prompt)

            if not raw_input.strip():
                continue

            if raw_input.startswith("/"):
                try:
                    tokens = shlex.split(raw_input[1:])
                except ValueError as exc:
                    self._console.print(f"[bold red]error[/bold red]: {exc}")
                    continue
                try:
                    args = self._parser.parse_args(tokens)
                except SystemExit:
                    continue
                func = getattr(args, "func", None)
                if func is None:
                    self._parser.print_usage()
                    self._console.print("for help, run [cyan]/help[/cyan]")
                    continue
                try:
                    func(args)
                except Exception as exc:
                    self._console.print(f"[bold red]error[/bold red]: {exc}")
                    continue
            else:
                self._console.print(f"user entered: {raw_input}")

    def _print_preamble(self) -> None:
        """
        Print the preamble for the REPL.
        """
        rprint("=" * 80)
        rprint("[bold]NEWMAN[/bold] - A CLI-based REPL client for the MAIL protocol")
        rprint("For help: [cyan]/help[/cyan], [cyan]/?[/cyan]")
        rprint("To quit: [cyan]/exit[/cyan], [cyan]/quit[/cyan]")
        rprint("=" * 80)

    def _repl_prompt(self) -> str:
        """
        Get the prompt for the REPL.
        """
        prompt = "[cyan]mail[/cyan]::"
        id_str = f"[bold green]{self._user_id}[/bold green]" if self._user_id else "[yellow]{unknown}[/yellow]"
        role_str = f"[bold green]{self._user_role}[/bold green]" if self._user_role else "[yellow]{unknown}[/yellow]"
        prompt += f"{role_str}:{id_str}@[bold green]{self.url}[/bold green]"
        prompt += "[white]$ [/white]"

        return prompt

    def _build_parser(self) -> ArgumentParser:
        """
        Build the argument parser for the REPL.
        """
        parser = ArgumentParser(
            prog="",
            usage="<command> [arguments]",
            description="A CLI-based REPL client for the MAIL protocol",
            epilog="Copyright (c) 2026 Addison Kline and the MAIL contributors" \
                 " (https://github.com/charonlabs/mail)",
        )
        subparsers = parser.add_subparsers(title="commands", dest="command")

        # command `exit`
        exit_desc = "Exit the REPL"
        exit_parser = subparsers.add_parser(
            "exit",
            aliases=["quit"],
            help=exit_desc,
            description=exit_desc,
        )
        exit_parser.set_defaults(func=self._cmd_exit)

        # command `help`
        help_desc = "Display help for commands"
        help_parser = subparsers.add_parser(
            "help", 
            aliases=["?"], 
            help=help_desc,
            description=help_desc,
        )
        help_parser.set_defaults(func=self._cmd_help)

        # command `ping`
        ping_desc = "Ping the MAIL server"
        ping_parser = subparsers.add_parser(
            "ping",
            help=ping_desc,
            description=ping_desc,
        )
        ping_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `GET /`",
        )
        ping_parser.set_defaults(func=self._cmd_ping)

        # command `login`
        login_desc = "Login to the MAIL server"
        login_parser = subparsers.add_parser(
            "login",
            help=login_desc,
            description=login_desc,
        )
        login_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `POST /login`",
        )
        login_parser.set_defaults(func=self._cmd_login)

        # command `swarm`
        swarm_desc = "Get the swarm of the MAIL server"
        swarm_parser = subparsers.add_parser(
            "swarm",
            help=swarm_desc,
            description=swarm_desc,
        )
        swarm_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `GET /swarm`",
        )
        swarm_parser.set_defaults(func=self._cmd_swarm)

        # command `registry`
        registry_desc = "Get the registry of the MAIL server"
        registry_parser = subparsers.add_parser(
            "registry",
            help=registry_desc,
            description=registry_desc,
        )
        registry_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `GET /registry`",
        )
        registry_parser.set_defaults(func=self._cmd_registry)

        # command `register`
        register_desc = "Register a remote swarm with the MAIL server"
        register_parser = subparsers.add_parser(
            "register",
            help=register_desc,
            description=register_desc,
        )
        register_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `POST /registry`",
        )
        register_parser.set_defaults(func=self._cmd_register)

        # command `deregister`
        deregister_desc = "Deregister a remote swarm from the MAIL server"
        deregister_parser = subparsers.add_parser(
            "deregister",
            help=deregister_desc,
            description=deregister_desc,
        )
        deregister_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `DELETE /registry/{swarm_name}`",
        )
        deregister_parser.set_defaults(func=self._cmd_deregister)

        return parser

    def _cmd_help(self, _args: Namespace) -> None:
        """
        Display help for commands.
        """
        self._parser.print_help()

    def _cmd_exit(self, _args: Namespace) -> None:
        """
        Exit the REPL.
        """
        self._console.print(f"disconnected from [bold green]{self.url}[/bold green]")
        raise SystemExit(0)

    def _cmd_login(self, args: Namespace) -> None:
        """
        Attempt to login to the MAIL server.
        """
        api_key = self._console.input("enter API key: ", password=True)
        try:
            response = self._client.login(api_key)
            if args.verbose:
                self._console.print(json.dumps(response.model_dump(), indent=2))
            else:
                self._console.print(f"logged in as [green]{response.user.role}:{response.user.name}[/green]")
        except Exception as exc:
            self._console.print(f"[bold red]error[/bold red]: {exc}")

    def _cmd_ping(self, args: Namespace) -> None:
        """
        Ping the MAIL server.
        """
        try:
            response = self._client.ping()
            if args.verbose:
                self._console.print(json.dumps(response.model_dump(), indent=2))
            else:
                self._console.print("pong")
        except Exception as exc:
            self._console.print(f"[bold red]error[/bold red]: {exc}")

    def _cmd_swarm(self, args: Namespace) -> None:
        """
        Get the swarm of the MAIL server.
        """
        try:
            response = self._client.get_swarm()
            if args.verbose:
                self._console.print(json.dumps(response.model_dump(), indent=2))
            else:
                self._console.print(f"swarm: [green]{response.swarm.name}[/green]")
        except Exception as exc:
            self._console.print(f"[bold red]error[/bold red]: {exc}")

    def _cmd_registry(self, args: Namespace) -> None:
        """
        Get the registry of the MAIL server.
        """
        try:
            response = self._client.get_registry()
            if args.verbose:
                self._console.print(json.dumps(response.model_dump(), indent=2))
            else:
                self._console.print(f"registry: {len(response.swarms)} swarms")
        except Exception as exc:
            self._console.print(f"[bold red]error[/bold red]: {exc}")

    def _cmd_register(self, args: Namespace) -> None:
        """
        Register a remote swarm with the MAIL server.
        """
        try:
            response = self._client.register_swarm()
            if args.verbose:
                self._console.print(json.dumps(response.model_dump(), indent=2))
            else:
                self._console.print(f"swarm [green]{response.swarm.name}[/green] registered")
        except Exception as exc:
            self._console.print(f"[bold red]error[/bold red]: {exc}")

    def _cmd_deregister(self, args: Namespace) -> None:
        """
        Deregister a remote swarm from the MAIL server.
        """
        try:
            response = self._client.deregister_swarm()
            if args.verbose:
                self._console.print(json.dumps(response.model_dump(), indent=2))
            else:
                self._console.print(f"swarm [green]{response.swarm.name}[/green] deregistered")
        except Exception as exc:
            self._console.print(f"[bold red]error[/bold red]: {exc}")

def _verify_url(url: str) -> None:
    """
    Verify the given URL value is valid.
    """
    result = urlsplit(url)
    if result.scheme != "https" and result.scheme != "http" and result.scheme != "swarm":
        raise ValueError(f"Invalid URL scheme: {result.scheme}")
    if not result.netloc.strip():
        raise ValueError(f"Invalid URL netloc: {result.netloc}")



def run_client(args: Namespace) -> None:
    """
    Run the MAIL client.
    """
    url = args.url

    _verify_url(url)

    print(f"connecting to {url}...")
    newman = Newman(url)
    newman.run_repl()
    print(f"disconnected from {url}")
