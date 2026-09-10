'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Input } from 'antd';
import type { InputRef } from 'antd';
import styles from './index.module.scss';
import {
  IP_RANGE_LOCKED_PREFIX_OCTETS,
  IP_RANGE_MAX_SIZE,
  displayedIpFromOctets,
  ipOctetsFromValue,
  ipRangeSize,
  isIpRangeOrderValid,
  isIpRangeWithinLimit,
} from './ipRangeLimits';

interface IpSegment {
  value: string;
  type: string;
  disabled: boolean;
}

interface IpInputProps {
  value: string[];
  onChange: (val: string[]) => void;
}

const segmentsFromIp = (ip: string, type: string, lockPrefix: boolean): IpSegment[] =>
  ipOctetsFromValue(ip).map((octet, index) => ({
    value: octet,
    type,
    disabled: lockPrefix && index < IP_RANGE_LOCKED_PREFIX_OCTETS,
  }));

const IpInput: React.FC<IpInputProps> = ({ value = ['', ''], onChange }) => {
  const [beginFocus, setBeginFocus] = useState(false);
  const [endFocus, setEndFocus] = useState(false);
  const [beginError, setBeginError] = useState(false);
  const [endError, setEndError] = useState(false);
  const [beginIpAddress, setBeginIpAddress] = useState<IpSegment[]>(() =>
    segmentsFromIp(value[0] || '', 'beginInput', false)
  );
  // /21：仅锁定前 2 段；第 3、4 段可编辑（相对原 /24 仅末段可编辑）
  const [endIpAddress, setEndIpAddress] = useState<IpSegment[]>(() =>
    segmentsFromIp(value[1] || '', 'endInput', true)
  );

  const inputRefs = useRef<(InputRef | null)[]>([]);
  const beginValue = value?.[0] || '';
  const endValue = value?.[1] || '';

  useEffect(() => {
    const incoming = [beginValue, endValue];
    setBeginIpAddress((prev) =>
      displayedIpFromOctets(prev) === incoming[0]
        ? prev
        : segmentsFromIp(incoming[0], 'beginInput', false)
    );
    setEndIpAddress((prev) =>
      displayedIpFromOctets(prev) === incoming[1]
        ? prev
        : segmentsFromIp(incoming[1], 'endInput', true)
    );
  }, [beginValue, endValue]);

  const formatIpSegment = useCallback((raw: string) => {
    const num = parseInt(raw.trim(), 10);
    if (isNaN(num)) return '0';
    return Math.min(Math.max(num, 0), 255).toString();
  }, []);

  const handleKeyPress = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>, index: number, type: string) => {
      const totalLength = type === 'beginInput' ? 4 : 8;

      switch (e.key) {
        case '.':
        case 'ArrowRight':
          if (index < totalLength - 1) {
            e.preventDefault();
            inputRefs.current[index + 1]?.focus();
          }
          break;
        case 'ArrowLeft':
          if (index > 0) {
            e.preventDefault();
            inputRefs.current[index - 1]?.focus();
          }
          break;
      }
    },
    []
  );

  const handleIpChange = useCallback(
    (ipSegments: IpSegment[], index: number, raw: string, type: string) => {
      const formattedValue = formatIpSegment(raw);
      const updatedIpSegments = ipSegments.map((segment, i) =>
        i === index ? { ...segment, value: formattedValue } : segment
      );

      if (type === 'beginInput') {
        const newBeginIp = updatedIpSegments
          .map((item) => item.value)
          .join('.');
        const updatedEndIpAddress = [...endIpAddress];
        for (let i = 0; i < IP_RANGE_LOCKED_PREFIX_OCTETS; i++) {
          updatedEndIpAddress[i] = {
            ...updatedEndIpAddress[i],
            value: updatedIpSegments[i].value,
          };
        }

        let newEndIp = updatedEndIpAddress.map((item) => item.value).join('.');
        // 起始变更导致顺序非法或超出 /21 时，将结束地址主机段对齐到起始地址
        if (
          !isIpRangeOrderValid(newBeginIp, newEndIp) ||
          (ipRangeSize(newBeginIp, newEndIp) > IP_RANGE_MAX_SIZE)
        ) {
          for (let i = IP_RANGE_LOCKED_PREFIX_OCTETS; i < 4; i++) {
            updatedEndIpAddress[i] = {
              ...updatedEndIpAddress[i],
              value: updatedIpSegments[i].value,
            };
          }
          newEndIp = updatedEndIpAddress.map((item) => item.value).join('.');
        }

        setBeginIpAddress(updatedIpSegments);
        setEndIpAddress(updatedEndIpAddress);
        setEndError(
          !isIpRangeOrderValid(newBeginIp, newEndIp) ||
            !isIpRangeWithinLimit(newBeginIp, newEndIp),
        );
        onChange([newBeginIp, newEndIp]);
      } else {
        const newEndIp = updatedIpSegments.map((item) => item.value).join('.');
        const newBeginIp = beginIpAddress.map((item) => item.value).join('.');
        setEndIpAddress(updatedIpSegments);

        const isValid =
          isIpRangeOrderValid(newBeginIp, newEndIp) &&
          isIpRangeWithinLimit(newBeginIp, newEndIp);
        setEndError(!isValid);
        onChange([newBeginIp, newEndIp]);
      }
    },
    [beginIpAddress, endIpAddress, onChange, formatIpSegment]
  );

  const validateIp = () => {
    const beginIp = value[0];
    const endIp = value[1];
    const reg =
      /^((2[0-4]\d|25[0-5]|[01]?\d\d?)\.){3}(2[0-4]\d|25[0-5]|[01]?\d\d?)$/;
    const orderInvalid = !isIpRangeOrderValid(beginIp, endIp);
    const sizeInvalid =
      reg.test(beginIp) &&
      reg.test(endIp) &&
      !isIpRangeWithinLimit(beginIp, endIp);
    setBeginError(!reg.test(beginIp));
    setEndError(!reg.test(endIp) || orderInvalid || sizeInvalid);
  };

  const handleFocus = (type: string) => {
    if (type === 'beginInput') {
      setBeginFocus(true);
    } else {
      setEndFocus(true);
    }
  };

  const handleBlur = () => {
    setBeginFocus(false);
    setEndFocus(false);
    validateIp();
  };

  return (
    <div className={styles['ip-input']}>
      <ul
        className={`${styles['ip-address']} ${beginFocus ? styles['focus-input'] : ''} ${
          beginError ? styles['error-input'] : ''
        }`}
      >
        {beginIpAddress.map((item, index) => (
          <li key={index}>
            <Input
              className={styles['ip-segment-input']}
              ref={(el) => {
                inputRefs.current[index] = el;
              }}
              type="text"
              value={item.value}
              onChange={(e) =>
                handleIpChange(beginIpAddress, index, e.target.value, item.type)
              }
              onKeyDown={(e) => handleKeyPress(e, index, item.type)}
              onFocus={() => handleFocus(item.type)}
              onBlur={handleBlur}
            />
            {index < 3 && <span className={styles.point} />}
          </li>
        ))}
      </ul>
      <span className={styles.line}>-</span>
      <ul
        className={`${styles['ip-address']} ${endFocus ? styles['focus-input'] : ''} ${
          endError ? styles['error-input'] : ''
        }`}
      >
        {endIpAddress.map((item, index) => (
          <li key={index}>
            <Input
              className={styles['ip-segment-input']}
              ref={(el) => {
                inputRefs.current[index + 4] = el;
              }}
              type="text"
              value={item.value}
              onChange={(e) =>
                handleIpChange(endIpAddress, index, e.target.value, item.type)
              }
              onKeyDown={(e) => handleKeyPress(e, index + 4, item.type)}
              onFocus={() => handleFocus(item.type)}
              onBlur={handleBlur}
              disabled={item.disabled}
            />
            {index < 3 && <span className={styles.point} />}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default IpInput;
