# Multi-Agent Interface Layer (MAIL) Specification

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
* [1 Abstract](#1-abstract)
* [2 Requirements Language](#2-requirements-language)
* [3 Motivation](#3-motivation)
  * [3.1 Goals For MAIL](#31-goals-for-mail)
  * [3.2 What MAIL Is Not](#32-what-mail-is-not)
* [4 Architecture Overview](#4-architecture-overview)
  * [4.1 MAIL Clients](#41-mail-clients)
  * [4.2 MAIL Servers](#42-mail-servers)
  * [4.3 MAIL Swarms](#43-mail-swarms)
* [5 User-Agents](#5-user-agents)
  * [5.1 Admins](#51-admins)
  * [5.2 Agents](#52-agents)
  * [5.3 Daemons](#53-daemons)
  * [5.4 Users](#54-users)
* [6 Addresses](#6-addresses)
  * [6.1 Host-Scoped Addresses](#61-host-scoped-addresses)
  * [6.2 Swarm-Scoped Addresses](#62-swarm-scoped-addresses)
* [7 Messages](#7-messages)
  * [7.1 Message IDs](#71-message-ids)
  * [7.2 Senders](#72-senders)
  * [7.3 Recipients](#73-recipients)
  * [7.4 Message Subjects](#74-message-subjects)
  * [7.5 Message Bodies](#75-message-bodies)
  * [7.6 Timestamps](#76-timestamps)
  * [7.7 Message Metadata](#77-message-metadata)
* [8 Delivery](#8-delivery)
  * [8.1 Pre-Send Errors](#81-pre-send-errors)
  * [8.2 Post-Send Errors](#82-post-send-errors)
* [9 Security Considerations](#9-security-considerations)
  * [9.1 MAIL Clients](#91-mail-clients)
  * [9.2 MAIL Daemons](#92-mail-daemons)
  * [9.3 MAIL Servers](#93-mail-servers)
  * [9.4 MAIL User-Agents](#94-mail-user-agents)
* [10 Versioning](#10-versioning)
* [11 References](#11-references)

## 1. Abstract

The Multi-Agent Interface Layer (MAIL) is an open protocol that defines a text-based, email-like communication layer for human users and AI agents alike.
More specifically, it defines a suite of data structure primitives, an HTTP contract for server-client interaction, and associated rules and terminology.

## 2. Requirements Language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED",  "MAY", and "OPTIONAL" in this document are to be interpreted as described in [RFC 2119][rfc-2119].

## 3. Motivation

In a world where AI agents are increasingly capable of handling long-running, complex tasks, the need for standardized contracts covering inter-agent communication is more palpable than ever.
While MAIL v1 defined contracts for inter-agent messaging, it also defined strict standards for multi-agent systems in general, including their runtime environment and tool usage.
However, as of 2026, the flaws in this approach became readily apparent.
The success of terminal-based agents like [OpenClaw][openclaw] demonstrates that AI agents no longer need to have their runtime and execution environments defined in the same place as their communication contract.
As a result, MAIL v2 much more explicitly covers the communication layer between AI agents, and as little as possible beyond that.

### 3.1. Goals For MAIL

- **Focus on communication.** MAIL is, at its core, a communication protocol. Areas outside the scope of communication (agent runtime, tool execution, etc.) SHOULD NOT be defined and handled by MAIL itself.
- **Don't reinvent the wheel.** There are plenty of existing standards covering topics like server-client communication, authentication, data formatting, and more. MAIL SHOULD NOT define contracts for such topics when standards already exist and can be built off of.

### 3.2. What MAIL Is Not

- **MAIL is not an agent runtime.** Rather than impose restrictions on how AI agents can exist and act autonomously, MAIL focuses explicitly on the communication layer between multiple agents.
- **MAIL is not a monolithic standard for all inter-agent communication.** MAIL is designed to mirror email and its associated standards that have existed for decades. However, just as humans can digitally communicate by means beyond just email, AI agents are by no means required to use MAIL for *all* inter-agent communication. Just like humans, AI agents want to use the best tool for the job, whatever that may be.

## 4. Architecture Overview

MAIL defines a standard for email-like communication between AI agents and human users alike by allowing user-agents to compose and send messages to one another.
Like in modern email, MAIL user-agents have their own addresses and associated inboxes where messages sent to them can be delivered.
The MAIL server is in charge of managing user-agent authentication, message boxes, drafts, and the first and last stages of message delivery.
Message delivery is handled largely by MAIL daemons, rather than the server itself.

### 4.1. MAIL Clients

A MAIL client is software that can connect to a MAIL server over [HTTP(S)][http-specs] to provide access to authorized user-agent(s).
MAIL clients MUST support the endpoints and data models defined by the authoritative MAIL HTTP contract in [openapi.yaml](openapi.yaml).
MAIL clients MAY provide extra functionality beyond what is required by the OpenAPI spec.
Implementers SHOULD heed to the MAIL client security considerations in [Section 9.1](#91-mail-clients).

### 4.2. MAIL Servers

A MAIL server is an HTTP server that conforms to the authoritative contract in [openapi.yaml](openapi.yaml).
MAIL servers MAY provide extra functionality beyond what is required by the OpenAPI spec.
Implementers SHOULD heed to the MAIL server security considerations in [Section 9.3](#93-mail-servers).

### 4.3. MAIL Swarms

A MAIL swarm is an abstract collection of agent addresses, mailing lists, and associated metadata existing within a MAIL server.
Swarms SHOULD be used to scope discrete multi-agent deployments within a MAIL server.
Swarms MUST be representable by the `MAILSwarm` schema defined in [openapi.yaml](openapi.yaml).

## 5. User-Agents

A MAIL user-agent is an authorized client communicating with a specified MAIL server.
This category encompasses both human users and AI agents, as well as autonomous daemons tasked with message delivery.

### 5.1. Admins

A MAIL admin is a user-agent with server-level administrator privileges beyond those of other user-agent types.
Admins MAY use all the same MAIL server functionalities that agents and users can.
Every MAIL admin MUST have a host-scoped address (see [Section 6.1](#61-host-scoped-addresses)).
Implementers SHOULD exercise extreme caution when generating and handing out admin credentials.

### 5.2. Agents

A MAIL agent is a user-agent category reserved for AI agents.
Agents MAY compose and send messages to other user-agents, subscribe to/unsubscribe from mailing lists, and access limited server metadata.
Every MAIL agent MUST have a swarm-scoped address (see [Section 6.2](#62-swarm-scoped-addresses)).

### 5.3. Daemons

A MAIL daemon is a user-agent tasked with delivering messages between authorized user-agents.
Daemons MUST NOT tamper with, modify, or otherwise alter the contents of the MAIL messages they deliver.
Daemons SHOULD NOT be able to compose and send messages of their own.
Every MAIL daemon MUST have a host-scoped address (see [Section 6.1](#61-host-scoped-addresses)).
Implementers SHOULD exercise extreme caution when generating and handing out admin credentials.

### 5.4. Users

A MAIL user is a user-agent category reserved for human users of a MAIL swarmer without administrator privileges.
Users MAY compose and send messages to other user-agents, subscribe to/unsubscribe from mailing lists, and access limited server metadata.
Every MAIL user MUST have a host-scoped address (see [Section 6.1](#61-host-scoped-addresses)).

## 6. Addresses

A MAIL address is a unique identifying string for a given user-agent or delivery target.
Depending on the type of user-agent or delivery target, a MAIL address MUST be either host-scoped or swarm-scoped.

### 6.1. Host-Scoped Addresses

Host-scoped addresses are MAIL addresses defined at the level of the MAIL server, rather than a server-owned swarm.
These follow the format `{ua_type}:{ua_id}@{host}`, where:
- **ua_type**: The user-agent type. MUST be one of `admin`, `daemon`, `user`.
- **ua_id**: The user-agent's unique ID. See below for more info.
- **host**: The domain name of the MAIL server host, e.g. `example.com`. For the sake of brevity and readability, fully-qualified domain names (e.g. `mail.example.com`) SHOULD be avoided.

All MAIL admins MUST have an address following the format `admin:{admin_id}@{host}`, where:
- **admin_id**: The unique identifier of a given MAIL server administrator. This value MUST be unique within a given MAIL server, i.e., no other admins have this same ID. This value MUST be a slug string. It MUST be at least 1 character in length, and SHOULD be no longer than 32 characters in total.
- **host**: See definition above.

All MAIL daemons MUST have an address following the format `daemon:{worker_name}@{host}`, where:
- **worker_name**: The unique identifier of a given MAIL server daemon. This value MUST be unique within a given MAIL server, i.e., no other daemons have this same worker name. This value MUST be a slug string. It MUST be at least 1 character in length, and SHOULD be no longer than 32 characters in total.
- **host**: See definition above.

All MAIL users MUST have an address following the format `user:{user_id}@{host}`, where:
- **user_id**: The unique identifier of a given MAIL server user. This value MUST be unique within a given MAIL server, i.e., no other users have this same ID. This value MUST be a slug string. It MUST be at least 1 character in length, and SHOULD be no longer than 32 characters in total.
- **host**: See definition above.

### 6.2. Swarm-Scoped Addresses

Swarm-scoped addresses are MAIL addresses defined at the level of a swarm existing inside a MAIL server.
These follow the format `{address_id}@{swarm}@{host}`, where:
- **address_id**: The unique identifier of a given MAIL swarm address. MUST be one of `{agent}`, `list:{list_id}` (see below for more info).
- **swarm**: The name of the swarm on a given MAIL server. This value MUST be unique, i.e., no other swarms on this server have this same name. This value MUST be a slug string. It MUST be at least 1 character in length, and SHOULD be no longer than 32 characters in total.
- **host**: See definition above.

All MAIL agents MUST have an address following the format `{agent}@{swarm}@{host}`, where:
- **agent**: The identifier of a given agent within a MAIL swarm. This value MUST be unique within a swarm, but MAY be shared by one or more agents on different swarms (e.g., `supervisor@swarm-1@example.com` and `supervisor@swarm-2@example.com` can coexist). This value MUST be a slug string. It MUST be at least 1 character in length, and SHOULD be no longer than 32 characters in total.
- **swarm**: See definition above.
- **host**: See definition above.

All MAIL mailing lists MUST have an address following the format `list:{list_id}@{swarm}@{host}`, where:
- **list_id**: The identifier of a given mailing list within a MAIL swarm. This value MUST be unique within a swarm, but MAY be shared by one or more lists on different swarms (e.g., `list:all@swarm-1@example.com` and `list:all@swarm-2@example.com` can coexist). This value MUST be a slug string. It MUST be at least 1 character in length, and SHOULD be no longer than 32 characters in total.
- **swarm**: See definition above.
- **host**: See definition above.

## 7. Messages

A MAIL message is an atomic unit of data that can be delivered from one MAIL address to another.
It is the basis for inter-agent communication in MAIL.
Over the wire, MAIL messages MUST exist as JSON strings; the authoritative data contract is defined by `MAILMessage` in [openapi.yaml](openapi.yaml).

### 7.1. Message IDs

Every MAIL message MUST have a unique identifier string, keyed by `message_id`. This value MUST be a [UUID][rfc-9562]. Message IDs SHOULD be generated upon message creation.

### 7.2. Senders

Every MAIL message MUST contain the address string of its sender, keyed by `sender`. This value MUST be a valid MAIL address per [Section 6](#6-addresses).

### 7.3. Recipients

Every MAIL message MUST contain the intended recipient address(es) determined by its sender, keyed by `recipients`. This array value MUST contain at least 1 entry. Each entry MUST be a valid MAIL address per [Section 6](#6-addresses).

### 7.4. Message Subjects

Every MAIL message MUST contain the subject string determined by its sender, keyed by `subject`. This value MUST be at least 1 character long, and SHOULD be no longer than 256 characters in total.

### 7.5. Message Bodies

Every MAIL message MUST contain the body string determined by its sender, keyed by `body`. This value MUST be at least 1 character long. No maximum character length is enforced by this spec; implementers SHOULD decide on their own limit to enforce (the reference implementation uses a body size limit of 65535 characters).

### 7.6. Timestamps

Every MAIL message MUST contain the timestamp string of the time it was sent by its sender, keyed by `sent_at`. This value MUST be a UTC timestamp as defined by [RFC 3339][rfc-3339].

### 7.7. Message Metadata

Every MAIL message MUST contain a field for implementer-defined message metadata, defined by `metadata`. This value MAY be an empty object (`{}`). Implementer-defined message data MUST be stored in the `metadata` field, rather than in the top level of the `MAILMessage` object itself.

## 8. Delivery

When a user-agent creates and sends a MAIL message, the new message is stored on the MAIL server, but is not yet delivered to the specified recipient(s).
Said message MUST be delivered to its intended recipient(s) by an authorized MAIL daemon as described in [Section 5.3](#53-daemons).

### 8.1. Pre-Send Errors

If an authorized user-agent attempts to create a message with a malformed subject (per [Section 7.4](#74-message-subjects)), the desired message MUST NOT be created and the user-agent MUST be notified.
If an authorized user-agent attempts to create a message with a malformed body (per [Section 7.5](#75-message-bodies)), the desired message MUST NOT be created and the user-agent MUST be notified.
If an authorized user-agent's message contains one or more malformed MAIL addresses (per [Section 6](#6-addresses)), the message MUST NOT be delivered and the sending user-agent MUST be notified.

### 8.2. Post-Send Errors

If a valid MAIL message cannot be delivered to one or more intended recipients by an authorized daemon, the message MUST be preserved and the error SHOULD be logged by the daemon.

## 9. Security Considerations

### 9.1. MAIL Clients

CLI client implementers SHOULD only accept user-agent credentials via environment variables rather than command-line arguments to avoid exposing secrets in shell history.
Raw MAIL message contents SHOULD NOT be logged or stored by clients; if local message storage is necessary, implementers SHOULD encrypt messages to avoid exposing potentially-sensitive message content in plain text.

### 9.2. MAIL Daemons

CLI daemon implementers SHOULD only accept daemon credentials via environment variables rather than command-line arguments to avoid exposing secrets in shell history.
MAIL message contents, while often managed by the daemon, SHOULD NOT be logged.

### 9.3. MAIL Servers 

[TLS][rfc-8446] SHOULD be used in deployment of production MAIL servers.
Sensitive user-agent data (e.g. passwords or authentication tokens) SHOULD NOT be logged by the server.
Production MAIL servers SHOULD be deployed behind a reverse proxy to handle tasks like load balancing and rate-limiting.

### 9.4. MAIL User-Agents

MAIL user-agents SHOULD update their passwords at regular intervals to minimize the risk of unauthorized account access.

## 10. Versioning

All versions of the MAIL protocol MUST follow the format `{major}.{minor}`, where:
- **major**: The major protocol version. This value MUST be a positive integer. Major protocol changes MUST increment this value by 1.
- **minor**: The minor protocol version. This value MUST be an integer greater than or equal to 0. Minor (i.e. non-breaking) protocol changes MUST increment this value by 1.

When a major protocol update occurs, the minor version MUST be reset to 0.

## 11. References

- [rfc-2119]: https://datatracker.ietf.org/doc/html/rfc2119
- [openclaw]: https://openclaw.ai/
- [http-specs]: https://httpwg.org/specs/
- [rfc-9562]: https://www.rfc-editor.org/info/rfc9562/
- [rfc-3339]: https://datatracker.ietf.org/doc/html/rfc3339
- [rfc-8446]: https://www.rfc-editor.org/info/rfc8446/
