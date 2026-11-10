package state

const (
	ErasureStreamKey        = "ops:rum:v2:erasure:requests"
	ReconcileStreamKey      = "ops:rum:v2:operations:requests"
	ControlAuditStreamKey   = "ops:rum:v2:control:audit"
	OperationKeyPrefix      = "ops:rum:v2:operations:"
	CommandKeyPrefix        = "ops:rum:v2:commands:"
	SessionActivityIndexKey = "ops:rum:v2:session:activity"
	SessionEndedKeyPrefix   = "ops:rum:v2:ended:"
	// AggregateRouteKeyPrefix is the shared admission set for aggregate routes.
	// The suffix is a hash of tenant and application. Members are admitted routes.
	AggregateRouteKeyPrefix = "ops:rum:v2:aggregate:routes:"
)

// SessionEndedKey is the snapshot written for one authoritative session.
// The rumsession Lua builds the same key from SessionEndedKeyPrefix.
func SessionEndedKey(sessionKey string) string {
	return SessionEndedKeyPrefix + sessionKey
}
