# AI SDK Reference Documentation

These files contain verified information extracted from `ai-sdk-llms.txt` for implementing the MAIL AI SDK provider.

**Start here:** [overview.md](./overview.md) - Complete guide with all fundamentals

**Implementation:** [../mail-ai-sdk-provider-v2.md](../mail-ai-sdk-provider-v2.md) - Corrected provider sketch (v1: [mail-ai-sdk-provider-sketch.md](./mail-ai-sdk-provider-sketch.md))

## Files

| File | Description |
|------|-------------|
| [overview.md](./overview.md) | **Complete guide** - All fundamentals for MAIL provider |
| [00-sketch-corrections.md](./00-sketch-corrections.md) | Corrections needed for the original provider sketch |
| [01-language-model-v3-interface.md](./01-language-model-v3-interface.md) | LanguageModelV3 interface, doGenerate/doStream signatures |
| [02-stream-part-types.md](./02-stream-part-types.md) | All stream part types and their structures |
| [03-tool-call-handling.md](./03-tool-call-handling.md) | Tool call format, multi-step execution |
| [04-provider-metadata-usage.md](./04-provider-metadata-usage.md) | providerMetadata, finish reasons, token usage |
| [05-message-prompt-format.md](./05-message-prompt-format.md) | LanguageModelV3Prompt, message roles, content parts |
| [06-baseline-architecture.md](./06-baseline-architecture.md) | SDK structure, Next.js pattern, data flow |

### Source Files

| File | Description |
|------|-------------|
| [ai-sdk-llms.txt](./ai-sdk-llms.txt) | Full AI SDK documentation (llms.txt) |
| [ai-sdk-custom-provider.md](./ai-sdk-custom-provider.md) | Custom provider docs from ai-sdk.dev |
| [mail-ai-sdk-provider-sketch.md](./mail-ai-sdk-provider-sketch.md) | Original v1 sketch (see v2 for corrected version) |

## Key Takeaways for MAIL Provider

### Stream Part Lifecycle
```
text-start(id) → text-delta(id, delta)* → text-end(id) → finish(finishReason, usage)
```

### V3 Structures

**finishReason** (object form):
```typescript
{ unified: 'stop' | 'length' | 'tool-calls' | 'error' | 'other', raw?: any }
```

**usage** (nested):
```typescript
{
  inputTokens: { total, noCache, cacheRead?, cacheWrite? },
  outputTokens: { total, text, reasoning? }
}
```

**tool-call**:
```typescript
{ type: 'tool-call', toolCallId: string, toolName: string, input: object }
```

### Provider Metadata
Use `providerMetadata.mail` for MAIL-specific data. This is the standard pattern used by all providers.

## Source

All line references have been verified against the source file. The `MockLanguageModelV3` examples (lines 12759-12922) are the authoritative reference for V3 format.
