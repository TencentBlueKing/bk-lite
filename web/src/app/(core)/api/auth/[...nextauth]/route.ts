import NextAuth from "next-auth";
import { getAuthOptions } from "@/constants/authOptions";

const handler = (NextAuth as any)(await getAuthOptions());

export { handler as GET, handler as POST };