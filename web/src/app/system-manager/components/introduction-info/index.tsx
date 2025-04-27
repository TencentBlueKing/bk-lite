"use client";

import React from "react";
import introductionInfoStly from "./index.module.scss";
interface IntroductionInfoProp {
  message: string;
  title: string;
}
const IntroductionInfo: React.FC<IntroductionInfoProp> = ({ message, title }) => (
  <div className={`h-16 w-full mb-[30px] rounded-md ${introductionInfoStly.introductionInfo}`}>
    <h1 className="text-base font-sans ml-[39px] pt-2">{title}</h1>
    <p className="text-sm ml-[39px] font-light whitespace-nowrap">{message}</p>
  </div>
);

export default IntroductionInfo;
