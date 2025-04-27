'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Input } from 'antd';
import type { InputRef } from 'antd';
import styles from './index.module.scss';

interface IpSegment {
  value: string;
  type: string;
  disabled: boolean;
}

interface IpInputProps {
  value: string[];
  onChange: (val: string[]) => void;
}

const IpInput: React.FC<IpInputProps> = ({ value = ['', ''], onChange }) => {
  const [beginFocus, setBeginFocus] = useState(false);
  const [endFocus, setEndFocus] = useState(false);
  const [beginError, setBeginError] = useState(false);
  const [endError, setEndError] = useState(false);
  const [beginIpAddress, setBeginIpAddress] = useState<IpSegment[]>([
    { value: '', type: 'beginInput', disabled: false },
    { value: '', type: 'beginInput', disabled: false },
    { value: '', type: 'beginInput', disabled: false },
    { value: '', type: 'beginInput', disabled: false },
  ]);
  const [endIpAddress, setEndIpAddress] = useState<IpSegment[]>([
    { value: '', type: 'endInput', disabled: true },
    { value: '', type: 'endInput', disabled: true },
    { value: '', type: 'endInput', disabled: true },
    { value: '', type: 'endInput', disabled: false },
  ]);

  const inputRefs = useRef<(InputRef | null)[]>([]);
  const prevValueRef = useRef(value);

  useEffect(() => {
    if (
      value?.length &&
      (value[0] !== prevValueRef.current[0] ||
        value[1] !== prevValueRef.current[1])
    ) {
      const beginIp = value[0].split('.');
      const endIp = value[1].split('.');

      setBeginIpAddress((prev) =>
        prev.map((item, index) => ({
          ...item,
          value: beginIp[index] || '',
        }))
      );

      setEndIpAddress((prev) =>
        prev.map((item, index) => ({
          ...item,
          value: endIp[index] || '',
        }))
      );

      prevValueRef.current = value;
    }
  }, [value]);

  const validateIpRange = useCallback((beginIp: string, endIp: string) => {
    const ipToNumber = (ip: string) =>
      ip.split('.').reduce((acc, curr) => acc * 256 + parseInt(curr, 10), 0);

    if (!beginIp || !endIp) return true;
    return ipToNumber(endIp) >= ipToNumber(beginIp);
  }, []);

  const formatIpSegment = useCallback((value: string) => {
    const num = parseInt(value.trim(), 10);
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
    (ipSegments: IpSegment[], index: number, value: string, type: string) => {
      const formattedValue = formatIpSegment(value);
      const updatedIpSegments = ipSegments.map((segment, i) =>
        i === index ? { ...segment, value: formattedValue } : segment
      );

      if (type === 'beginInput') {
        const newBeginIp = updatedIpSegments
          .map((item) => item.value)
          .join('.');
        const updatedEndIpAddress = [...endIpAddress];
        for (let i = 0; i < 3; i++) {
          updatedEndIpAddress[i] = {
            ...updatedEndIpAddress[i],
            value: updatedIpSegments[i].value,
          };
        }
        setBeginIpAddress(updatedIpSegments);
        setEndIpAddress(updatedEndIpAddress);
        const newEndIp = `${newBeginIp.split('.').slice(0, 3).join('.')}.${endIpAddress[3].value}`;
        onChange([newBeginIp, newEndIp]);
      } else {
        const newEndIp = updatedIpSegments.map((item) => item.value).join('.');
        const newBeginIp = beginIpAddress.map((item) => item.value).join('.');
        setEndIpAddress(updatedIpSegments);

        if (!validateIpRange(newBeginIp, newEndIp)) {
          setEndError(true);
        } else {
          setEndError(false);
          onChange([newBeginIp, newEndIp]);
        }
      }
    },
    [beginIpAddress, endIpAddress, onChange, formatIpSegment, validateIpRange]
  );

  const validateIp = () => {
    const beginIp = value[0];
    const endIp = value[1];
    const reg =
      /^((2[0-4]\d|25[0-5]|[01]?\d\d?)\.){3}(2[0-4]\d|25[0-5]|[01]?\d\d?)$/;
    const flag =
      Number(endIp.replace(/\./g, '')) < Number(beginIp.replace(/\./g, ''));
    setBeginError(!reg.test(beginIp));
    setEndError(!reg.test(endIp) || flag);
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
