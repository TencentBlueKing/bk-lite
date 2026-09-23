package controller

import "github.com/bk-lite/rum-collector/pkg/rum/wire"

const (
	APIVersion = wire.APIVersion

	SubjectApplicationApply   = wire.SubjectApplicationApply
	SubjectApplicationGet     = wire.SubjectApplicationGet
	SubjectApplicationList    = wire.SubjectApplicationList
	SubjectApplicationRotate  = wire.SubjectApplicationRotate
	SubjectApplicationRetire  = wire.SubjectApplicationRetire
	SubjectApplicationDisable = wire.SubjectApplicationDisable
	SubjectErasureSubmit      = wire.SubjectErasureSubmit
	SubjectReconcileSubmit    = wire.SubjectReconcileSubmit
	SubjectOperationGet       = wire.SubjectOperationGet
	SubjectStatusGet          = wire.SubjectStatusGet
	QueueGroupController      = wire.QueueGroupController

	ErrorInvalidArgument     = wire.ErrorInvalidArgument
	ErrorNotFound            = wire.ErrorNotFound
	ErrorRevisionConflict    = wire.ErrorRevisionConflict
	ErrorIdempotencyConflict = wire.ErrorIdempotencyConflict
	ErrorOrgConflict         = wire.ErrorOrgConflict
	ErrorForbidden           = wire.ErrorForbidden
	ErrorUnavailable         = wire.ErrorUnavailable
	ErrorInternal            = wire.ErrorInternal
)

var (
	AllSubjects   = wire.AllSubjects
	DecodeRequest = wire.DecodeRequest
	Fingerprint   = wire.Fingerprint
	ErrorResponse = wire.ErrorResponse
)

type RequestEnvelope = wire.RequestEnvelope
type ResponseEnvelope = wire.ResponseEnvelope
type ResponseError = wire.ResponseError
type ErrorCode = wire.ErrorCode
type Budgets = wire.Budgets
type ApplicationApplyPayload = wire.ApplicationApplyPayload
type ApplicationPayload = wire.ApplicationPayload
type ApplicationRotatePayload = wire.ApplicationRotatePayload
type ApplicationRetirePayload = wire.ApplicationRetirePayload
type ErasureIdentity = wire.ErasureIdentity
type ErasureSubmitPayload = wire.ErasureSubmitPayload
type ReconcileSubmitPayload = wire.ReconcileSubmitPayload
type OperationGetPayload = wire.OperationGetPayload
type ApplicationView = wire.ApplicationView
type OperationView = wire.OperationView

func DecodePayload[T any](request RequestEnvelope) (T, error) {
	return wire.DecodePayload[T](request)
}
