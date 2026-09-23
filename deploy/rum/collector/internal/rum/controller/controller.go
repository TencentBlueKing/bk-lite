package controller

import (
	"context"
	"errors"
	"sync"

	"github.com/nats-io/nats.go"
)

type Controller struct {
	connection *nats.Conn
	service    *Service

	mu            sync.Mutex
	subscriptions []*nats.Subscription
}

func NewController(connection *nats.Conn, service *Service) *Controller {
	return &Controller{connection: connection, service: service}
}

func (controller *Controller) Start() error {
	if controller.connection == nil || controller.service == nil {
		return errors.New("controller requires NATS and control service")
	}
	controller.mu.Lock()
	defer controller.mu.Unlock()
	if len(controller.subscriptions) > 0 {
		return nil
	}
	for _, subject := range AllSubjects {
		subject := subject
		subscription, err := controller.connection.QueueSubscribe(
			subject,
			QueueGroupController,
			func(message *nats.Msg) {
				if message.Reply == "" {
					return
				}
				response := controller.service.Handle(context.Background(), subject, message.Data)
				_ = message.Respond(response)
			},
		)
		if err != nil {
			for _, active := range controller.subscriptions {
				_ = active.Unsubscribe()
			}
			controller.subscriptions = nil
			return err
		}
		if err := subscription.SetPendingLimits(1024, 8<<20); err != nil {
			_ = subscription.Unsubscribe()
			for _, active := range controller.subscriptions {
				_ = active.Unsubscribe()
			}
			controller.subscriptions = nil
			return err
		}
		controller.subscriptions = append(controller.subscriptions, subscription)
	}
	return controller.connection.Flush()
}

func (controller *Controller) Drain() error {
	controller.mu.Lock()
	subscriptions := controller.subscriptions
	controller.subscriptions = nil
	controller.mu.Unlock()
	var joined error
	for _, subscription := range subscriptions {
		joined = errors.Join(joined, subscription.Drain())
	}
	if controller.connection != nil {
		joined = errors.Join(joined, controller.connection.Flush())
	}
	return joined
}
