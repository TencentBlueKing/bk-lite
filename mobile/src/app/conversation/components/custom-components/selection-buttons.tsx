import React, { memo, useState } from 'react';
import { Button } from 'antd-mobile';

export interface SelectionButton {
    id: string;
    text: string;
    message: string; // 点击后发送的消息
}

export interface SelectionButtonsProps {
    buttons: SelectionButton[];
    onButtonClick?: (message: string) => void;
    layout?: 'vertical' | 'horizontal'; // 布局方向
}

const SelectionButtonsComponent: React.FC<SelectionButtonsProps> = ({
    buttons,
    onButtonClick,
    layout = 'vertical'
}) => {
    const [selectedId, setSelectedId] = useState<string | null>(null);

    const handleClick = (button: SelectionButton) => {
        if (selectedId) return; // 已选择,不再响应

        setSelectedId(button.id);
        if (onButtonClick) {
            onButtonClick(button.message);
        }
    };

    const containerClass = layout === 'horizontal'
        ? 'flex flex-row gap-2 flex-wrap'
        : 'flex flex-col gap-2';

    return (
        <div className="w-full">
            <div className="bg-[var(--color-fill-2)] rounded-2xl p-4">
                <div className={containerClass}>
                    {buttons.map((button) => (
                        <Button
                            key={button.id}
                            color={selectedId === button.id ? 'primary' : selectedId ? 'default' : 'primary'}
                            block={layout === 'vertical'}
                            disabled={selectedId !== null}
                            onClick={() => handleClick(button)}
                            className="rounded-lg"
                            style={
                                {
                                    '--adm-font-size-9': '15px',
                                    ...(layout === 'horizontal' ? { flex: '1 1 auto' } : {})
                                } as React.CSSProperties
                            }
                        >
                            {button.text}
                        </Button>
                    ))}
                </div>
            </div>
        </div>
    );
};

export const SelectionButtons = memo(SelectionButtonsComponent);
