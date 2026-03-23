# Webhook Bot Implementation Checklist

Use this checklist to guide your webhook integration implementation with either Feishu or DingTalk.

## Phase 1: Planning & Setup (Pre-Implementation)

### Project Definition
- [ ] **Define use cases**: What notifications/messages will be sent?
- [ ] **Choose platform**: Feishu or DingTalk (see COMPARISON.md)
- [ ] **Identify scope**: Single bot or multiple bots?
- [ ] **Plan message types**: What formats needed (text, markdown, cards)?
- [ ] **Document requirements**: Create technical specification
- [ ] **Identify team members**: Who will implement and maintain?

### Infrastructure Planning
- [ ] **HTTPS endpoint planned**: Location of webhook receiver
- [ ] **Server capacity assessed**: Can handle expected load?
- [ ] **Monitoring planned**: How will you track failures?
- [ ] **Backup plan**: What if webhook API is down?
- [ ] **Security reviewed**: IP whitelist, secret management strategy
- [ ] **Environment prepared**: Dev, staging, production?

### Credential Management Plan
- [ ] **Secrets management**: Where will credentials be stored?
- [ ] **Rotation schedule**: How often to rotate secrets?
- [ ] **Access control**: Who has credential access?
- [ ] **Audit logging**: How will credential usage be logged?
- [ ] **Incident response**: Plan if credentials are leaked

## Phase 2: Platform Setup

### Feishu Setup
- [ ] **Create Feishu account/team**: Registration complete
- [ ] **Create group chat**: Target chat for bot created
- [ ] **Create custom bot**: Added bot to group
- [ ] **Obtain webhook URL**: Copied from bot settings
- [ ] **Copy secret key**: If signature verification enabled
- [ ] **Document credentials**: Stored securely
- [ ] **Configure IP whitelist**: If organization requires
- [ ] **Test webhook URL**: With curl to verify

### DingTalk Setup
- [ ] **Create DingTalk account/team**: Registration complete
- [ ] **Create group chat**: Target chat for bot created
- [ ] **Create custom bot**: Through group settings
- [ ] **Obtain webhook URL**: Access token copied
- [ ] **Copy secret key**: Signature secret saved
- [ ] **Document credentials**: Stored securely
- [ ] **Configure IP whitelist**: If organization requires
- [ ] **Test webhook URL**: With curl to verify

## Phase 3: Authentication Implementation

### Signature Verification Setup
- [ ] **Understand algorithm**: Read signature verification docs
- [ ] **Implement signature generation**: In your language
- [ ] **Implement signature verification**: On webhook endpoint
- [ ] **Test signature verification**: With known values
- [ ] **Add timestamp validation**: Check request timestamp
- [ ] **Add replay attack prevention**: Log processed webhooks
- [ ] **Test with both systems**: Verify in dev environment

### Secret Key Management
- [ ] **Store securely**: Use environment variables or secrets manager
- [ ] **Never log**: Ensure secrets never appear in logs
- [ ] **Rotate regularly**: Schedule quarterly or more often
- [ ] **Document rotation process**: Clear procedure documented
- [ ] **Access control**: Limit who can access secrets
- [ ] **Audit trail**: Log who rotates secrets

## Phase 4: Basic Message Implementation

### Text Messages
- [ ] **Implement text message function**: Basic send capability
- [ ] **Test with curl first**: Manual verification
- [ ] **Test in code**: Programmatic send
- [ ] **Verify in chat**: Message appears correctly
- [ ] **Test special characters**: Unicode, emojis, etc.
- [ ] **Test message limits**: Max length handling
- [ ] **Add error handling**: Graceful failure handling
- [ ] **Add retry logic**: Automatic retry on failure

### Markdown/Rich Text
- [ ] **Implement formatted message function**: Markdown/post type
- [ ] **Test basic formatting**: Bold, italic, links
- [ ] **Test complex formatting**: Nested elements, mixed types
- [ ] **Verify rendering**: Check appearance in chat
- [ ] **Test with URLs**: Links work correctly
- [ ] **Test with mentions**: AT mentions work (DingTalk)
- [ ] **Add error handling**: Invalid markdown handling
- [ ] **Document format specs**: Clear examples for team

### Images & Media
- [ ] **Implement image message function**: Image sending
- [ ] **Test image upload**: If applicable to platform
- [ ] **Test image URLs**: External image links
- [ ] **Verify image display**: Proper rendering in chat
- [ ] **Test different formats**: PNG, JPG, GIF support
- [ ] **Handle large files**: Compression if needed
- [ ] **Add fallback text**: For when images fail to load

## Phase 5: Advanced Features

### Interactive Cards (Feishu)
- [ ] **Learn card JSON structure**: Study documentation
- [ ] **Implement simple card**: Basic button card
- [ ] **Implement complex card**: Multiple elements
- [ ] **Test all card types**: Button, dropdown, date picker
- [ ] **Test color templates**: Different styling options
- [ ] **Test card actions**: Button click callbacks
- [ ] **Implement action handlers**: Process card responses
- [ ] **Add validation**: Card JSON validation
- [ ] **Test edge cases**: Very long text, many buttons
- [ ] **Document card patterns**: Save templates for reuse

### Action Cards (DingTalk)
- [ ] **Learn action card structure**: Study documentation
- [ ] **Implement action card**: Basic button action card
- [ ] **Test button actions**: Click functionality
- [ ] **Implement multiple buttons**: More than 2 buttons
- [ ] **Test feed cards**: News feed format
- [ ] **Test OA cards**: OA template format
- [ ] **Add error handling**: Invalid card handling
- [ ] **Document patterns**: Save templates for team

### Advanced Message Types
- [ ] **Research available types**: Understand all options
- [ ] **Implement voice messages**: If applicable (DingTalk)
- [ ] **Implement file messages**: File attachments
- [ ] **Implement forward messages**: Share existing messages
- [ ] **Test all implemented types**: Each one individually
- [ ] **Create type selector**: Flexible message creation

## Phase 6: Error Handling & Resilience

### Error Handling Implementation
- [ ] **Document error codes**: Create reference guide
- [ ] **Implement error parsing**: Extract error from response
- [ ] **Add logging**: Log all errors with context
- [ ] **Implement user feedback**: Inform users of failures
- [ ] **Create error responses**: Structured error messages
- [ ] **Test error scenarios**: Simulate various failures
- [ ] **Add alerting**: Notification on critical errors
- [ ] **Monitor error rates**: Dashboard for errors

### Retry Logic
- [ ] **Implement exponential backoff**: Gradually increase wait time
- [ ] **Set max retries**: Reasonable retry limit (e.g., 3-5)
- [ ] **Add jitter**: Randomize retry timing
- [ ] **Test retry logic**: Verify behavior
- [ ] **Add circuit breaker**: Stop retrying after threshold
- [ ] **Log retry attempts**: Track retry history
- [ ] **Monitor retry metrics**: Dashboard tracking

### Rate Limiting
- [ ] **Understand platform limits**: Feishu 10/sec, DingTalk 20/min
- [ ] **Implement request queuing**: Queue excess requests
- [ ] **Add rate limit detection**: Detect 429 responses
- [ ] **Implement backoff**: Increase delay when rate limited
- [ ] **Monitor rates**: Dashboard of current usage
- [ ] **Add alerts**: Alert when approaching limits
- [ ] **Document limits**: Clear limits documented

## Phase 7: Webhook Receiver (Inbound)

### Webhook Endpoint Setup
- [ ] **Create HTTPS endpoint**: Secure webhook receiver
- [ ] **Implement request validation**: Check content-type, etc.
- [ ] **Implement signature verification**: Validate authenticity
- [ ] **Add timestamp validation**: Check request freshness
- [ ] **Add request logging**: Log all inbound requests
- [ ] **Implement response handling**: Return proper status
- [ ] **Add error handling**: Graceful error responses
- [ ] **Test with curl**: Simulate requests

### Event Processing
- [ ] **Identify event types**: What events platform sends
- [ ] **Parse event payload**: Extract relevant data
- [ ] **Implement event handlers**: Handle each event type
- [ ] **Add error handling**: Handle malformed events
- [ ] **Add validati
