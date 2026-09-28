//go:build !linux

package main

func applyResourceLimits(pid int, memBytes uint64) {}
