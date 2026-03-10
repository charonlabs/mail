# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2025 Addison Kline

import json
import os
import shlex
from argparse import ArgumentParser, Namespace
from re import L
from urllib.parse import urlsplit

from dotenv import load_dotenv
from rich import print as rprint
from rich.console import Console
from rich.prompt import Prompt

from .api import MAILClient

load_dotenv()


class Newman:
    """
    NEWMAN: A CLI-based REPL client for the MAIL protocol.
    """
    def __init__(
        self,
        url: str,
        api_key: str | None = None,
    ) -> None:
        self.url = url
        self._client = MAILClient(self.url)
        self._console = Console()
        self._parser = self._build_parser()

        if api_key is None:
            self._api_key = api_key
            self._user_id = None
            self._user_role = None
        else:
            response = self._client.login(api_key=api_key)
            self._api_key = response.access_token
            self._user_id = response.id
            self._user_role = response.role

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
        if not self._api_key:
            rprint("[bold yellow]warning[/bold yellow]: you are not currently logged in")
            rprint("[bold yellow]warning[/bold yellow]: you can login with [cyan]/login[/cyan]")
        else:
            rprint(f"logged in as [green]{self._user_role}:{self._user_id}[/green]")
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
            usage="/exit",
            help=exit_desc,
            description=exit_desc,
        )
        exit_parser.set_defaults(func=self._cmd_exit)

        # command `help`
        help_desc = "Display help for commands"
        help_parser = subparsers.add_parser(
            "help", 
            aliases=["?"], 
            usage="/help",
            help=help_desc,
            description=help_desc,
        )
        help_parser.set_defaults(func=self._cmd_help)

        # command `ping`
        ping_desc = "Ping the MAIL server"
        ping_parser = subparsers.add_parser(
            "ping",
            usage="/ping [options]",
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
            usage="/login [options]",
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

        # command `logout`
        logout_desc = "(admin|user) Logout from the MAIL server"
        logout_parser = subparsers.add_parser(
            "logout",
            usage="/logout",
            help=logout_desc,
            description=logout_desc,
        )
        logout_parser.set_defaults(func=self._cmd_logout)

        # command `whoami`
        whoami_desc = "(admin|user) Get the client's identity"
        whoami_parser = subparsers.add_parser(
            "whoami",
            usage="/whoami [options]",
            help=whoami_desc,
            description=whoami_desc,
        )
        whoami_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `GET /whoami`",
        )
        whoami_parser.set_defaults(func=self._cmd_whoami)

        # command `swarm`
        swarm_desc = "Get the swarm of the MAIL server"
        swarm_parser = subparsers.add_parser(
            "swarm",
            usage="/swarm [options]",
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
            usage="/registry [options]",
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
        register_desc = "(admin|user) Register a remote swarm with the MAIL server"
        register_parser = subparsers.add_parser(
            "register",
            usage="/register <base_url> <api_key_ref> [options]",
            help=register_desc,
            description=register_desc,
        )
        register_parser.add_argument(
            "base_url",
            type=str,
            help="the base URL of the remote swarm",
        )
        register_parser.add_argument(
            "api_key_ref",
            type=str,
            help="the API key reference of the remote swarm",
        )
        register_parser.add_argument(
            "-p",
            "--public",
            action="store_true",
            help="make the remote swarm public",
        )
        register_parser.add_argument(
            "-V",
            "--volatile",
            action="store_true",
            help="make the remote swarm volatile",
        )
        register_parser.add_argument(
            "-m",
            "--metadata",
            type=str,
            help="the metadata of the remote swarm",
        )
        register_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `POST /registry`",
        )
        register_parser.set_defaults(func=self._cmd_register)

        # command `deregister`
        deregister_desc = "(admin|user) Deregister a remote swarm from the MAIL server"
        deregister_parser = subparsers.add_parser(
            "deregister",
            usage="/deregister <swarm_name> [options]",
            help=deregister_desc,
            description=deregister_desc,
        )
        deregister_parser.add_argument(
            "swarm_name",
            type=str,
            help="the name of the remote swarm to deregister",
        )
        deregister_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `DELETE /registry/{swarm_name}`",
        )
        deregister_parser.set_defaults(func=self._cmd_deregister)

        # command `message`
        message_desc = "(admin|user) Send a message to the MAIL server"
        message_parser = subparsers.add_parser(
            "message",
            usage="/message <body> [options]",
            help=message_desc,
            description=message_desc,
        )
        message_parser.add_argument(
            "body",
            type=str,
            help="the message to send",
        )
        message_parser.add_argument(
            "-s",
            "--subject",
            default="New Message",
            type=str,
            help="the subject of the message",
        )
        message_parser.add_argument(
            "-t",
            "--msg-type",
            default="request",
            type=str,
            choices=["direct", "broadcast", "interrupt"],
            help="the type of the message",
        )
        message_parser.add_argument(
            "-tid",
            "--task-id",
            type=str,
            help="the task ID of the message",
        )
        message_parser.add_argument(
            "-r",
            "--recipients",
            type=str,
            nargs="+",
            default=[],
            help="the recipient agent(s) of the message",
        )
        message_parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            help="view the full JSON response for `POST /message`",
        )
        message_parser.set_defaults(func=self._cmd_message)

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
            self._api_key = response.access_token
            self._user_id = response.id
            self._user_role = response.role
            if args.verbose:
                self._console.print(json.dumps(response.model_dump(), indent=2))
            else:
                self._console.print(f"logged in as [green]{response.role}:{response.id}[/green]")
        except Exception as exc:
            self._console.print(f"[bold red]error[/bold red]: {exc}")

    def _cmd_logout(self, _args: Namespace) -> None:
        """
        Logout from the MAIL server.
        """
        try:
            if (self._user_role not in ["admin", "user"]) or (self._api_key is None) or (self._user_id is None):
                raise ValueError("not logged in")
            self._api_key = None
            self._user_id = None
            self._user_role = None
            self._console.print(f"logged out from [bold green]{self.url}[/bold green]")
        except Exception as exc:
            self._console.print(f"[bold red]error[/bold red]: {exc}")

    def _cmd_whoami(self, args: Namespace) -> None:
        """
        Get the client's identity.
        """
        try:
            response = self._client.whoami()
            if args.verbose:
                self._console.print(json.dumps(response.model_dump(), indent=2))
            else:
                self._console.print(f"role [green]{response.role}[/green] with ID [green]{response.id}[/green]")
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
            response = self._client.register_swarm(
                base_url=args.base_url,
                api_key_ref=args.api_key_ref,
                public=args.public,
                volatile=args.volatile,
                metadata=args.metadata,
            )
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
            response = self._client.deregister_swarm(args.swarm_name)
            if args.verbose:
                self._console.print(json.dumps(response.model_dump(), indent=2))
            else:
                self._console.print(f"swarm [green]{response.swarm.name}[/green] deregistered")
        except Exception as exc:
            self._console.print(f"[bold red]error[/bold red]: {exc}")

    def _cmd_message(self, args: Namespace) -> None:
        """
        Send a message to the MAIL server.
        """
        try:
            response = self._client.post_message(
                body=args.body,
                subject=args.subject,
                msg_type=args.msg_type,
                task_id=args.task_id,
                recipients=args.recipients,
                metadata=args.metadata,
            )
            if args.verbose:
                self._console.print(json.dumps(response.model_dump(), indent=2))
            else:
                self._console.print(response.message)
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
    api_key = os.getenv("MAIL_API_KEY") if not args.no_login else None

    _verify_url(url)
    
    print(f"connecting to {url}...")
    newman = Newman(url, api_key)
    newman.run_repl()
    print(f"disconnected from {url}")