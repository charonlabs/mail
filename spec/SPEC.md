# Multi-Agent Interface Layer Specification

- **Version**: 2.0
- **Date**: June 10, 2026
- **Status**: Open to feedback
- **Scope**: Defines a text-based, email-like communication layer for both human users and autonomous AI agents.
- **Authors**: 
  - **Addison Kline**
    - Affiliation: Charon Labs, LLC
    - GitHub: [@addisonkline](https://github.com/addisonkline)
  - **Ryan Heaton**
    - Affiliation: Charon Labs, LLC
    - GitHub: [@rheaton64](https://github.com/rheaton64)
  - **Will Hahn**
    - Affiliation: Charon Labs, LLC
    - GitHub: [@wsfhahn](https://github.com/wsfhahn)
  - **Jacob Hahn**
    - Affiliation: Charon Labs, LLC
    - GitHub: [@jacobtohahn](https://github.com/jacobtohahn)

## Table of Contents
* [Abstract](#abstract)
* [Terminology](#terminology)
  * [RFC 2119](#rfc-2119)
* [Motivation](#motivation)
  * [Goals for MAIL](#goals-for-mail)
  * [What MAIL is not](#what-mail-is-not)
* [Architecture Overview](#architecture-overview)
* [User-Agents](#user-agents)
  * [Admins](#admins)
  * [Agents](#agents)
  * [Daemons](#daemons)
  * [Users](#users)
* [Addressing](#addressing)
* [References](#references)

## Abstract

The Multi-Agent Interface Layer (MAIL) is an open protocol that defines a text-based, email-like communication layer for human users and AI agents alike.
More specifically, it defines a suite of data structure primitives, an HTTP contract for server-client interaction, and associated rules and terminology.

## Terminology

### RFC 2119

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED",  "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119][rfc-2119].

## Motivation

In a world where AI agents are increasingly capable of handling long-running, complex tasks, the need for standardized contracts covering inter-agent communication is more palpable than ever.
While MAIL v1 defined contracts for inter-agent messaging, it also defined strict standards for multi-agent systems in general, including their runtime environment and tool usage.
However, as of 2026, the flaws in this approach became readily apparent.
The success of terminal-based agents like [OpenClaw][openclaw] demonstrates that AI agents no longer need to have their runtime and execution environments defined in the same place as their communication contract.
As a result, MAIL v2 much more explicitly covers the communication layer between AI agents, and as little as possible beyond that.

### Goals for MAIL

- **Focus on communication.** MAIL is, at its core, a communication protocol. Areas outside the scope of communication (agent runtime, tool execution, etc.) need not be defined and handled by MAIL itself.
- **Don't reinvent the wheel.** MAIL need not define contracts for areas outside the scope of inter-agent communication. There are plenty of existing standards covering topics like server-client communication, authentication, and data formatting that make more sense to use and build off of rather than replace altogether.

### What MAIL is not

- **MAIL is not an agent runtime.** Rather than impose restrictions on how AI agents can exist and act autonomously, MAIL focuses explicitly on the communication layer between multiple agents.
- **MAIL is not a monolithic standard for all inter-agent communication.** MAIL is designed to mirror email and its associated standards that have existed for decades. However, just as humans can digitally communicate by means beyond just email, AI agents are by no means required to use MAIL for *all* inter-agent communication. Just like humans, AI agents want to use the best tool for the job, whatever that may be.

## Architecture Overview

MAIL defines a standard for email-like communication between AI agents and human users alike by allowing user-agents to compose and send messages to one another.
Like in modern email, MAIL user-agents have their own addresses and associated inboxes where messages sent to them can be delivered.
The MAIL server is in charge of managing user-agent authentication, message boxes, drafts, and the first and last stages of message delivery.
Message delivery is handled largely by MAIL daemons, rather than the server itself.

## User-Agents

A MAIL user-agent is an authorized client communicating with a specified MAIL server.
This category encompasses both human users and AI agents, as well as autonomous daemons tasked with message delivery.

### Admins

A MAIL admin is a user-agent with server-level administrator privileges beyond those of other user-agent types.
Admins MAY use all the same MAIL server functionalities that agents and users can.
Implementers SHOULD exercise extreme caution when generating and handing out admin credentials.

### Agents

A MAIL agent is a user-agent category reserved for AI agents.
Agents MAY compose and send messages to other user-agents, 

### Daemons

TODO

### Users

TODO

## Addressing

TODO

## References

- [rfc-2119]: https://datatracker.ietf.org/doc/html/rfc2119
- [openclaw]: https://openclaw.ai/
