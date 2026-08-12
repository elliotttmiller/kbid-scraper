import React, { useState, useRef, useEffect } from 'react';
import { MessageSquare, Send, Minimize2, Maximize2, Loader2, Bot } from 'lucide-react';
import { portfolioChat } from '../services/apiClient';
import { AnalyzedItem } from '../types';

interface ChatBotProps {
  analyzedItems: AnalyzedItem[];
}

interface Message {
  role: 'user' | 'model';
  text: string;
}

const ChatBot: React.FC<ChatBotProps> = ({ analyzedItems }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    { role: 'model', text: "I can summarize your analyzed lots, expected profit, risk, and bid limits." }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isOpen]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMsg = input;
    setInput('');
    setMessages(prev => [...prev, { role: 'user', text: userMsg }]);
    setIsLoading(true);

    try {
      const responseText = await portfolioChat(analyzedItems, userMsg);
      
      setMessages(prev => [...prev, { role: 'model', text: responseText || "I couldn't generate a response." }]);
    } catch (error) {
      console.error(error);
      setMessages(prev => [...prev, { role: 'model', text: "The valuation service is unavailable. Confirm the backend is running." }]);
    } finally {
      setIsLoading(false);
    }
  };

  if (!isOpen) {
    return (
      <button 
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 bg-blue-600 hover:bg-blue-500 text-white p-4 rounded-full shadow-lg shadow-blue-900/20 transition-transform hover:scale-105 z-40 flex items-center gap-2 border border-blue-500"
      >
        <MessageSquare size={24} />
        <span className="font-medium hidden sm:inline">Portfolio Summary</span>
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 w-96 h-[500px] bg-slate-900 rounded-xl shadow-2xl border border-slate-700 z-40 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="bg-blue-600 text-white p-4 flex justify-between items-center border-b border-blue-700">
        <div className="flex items-center gap-2">
          <Bot size={20} />
          <h3 className="font-semibold">Portfolio Summary</h3>
        </div>
        <button onClick={() => setIsOpen(false)} className="hover:bg-blue-700 p-1 rounded">
          <Minimize2 size={18} />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-950">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] p-3 rounded-lg text-sm ${
              msg.role === 'user' 
                ? 'bg-blue-600 text-white rounded-br-none' 
                : 'bg-slate-800 text-slate-200 border border-slate-700 rounded-bl-none shadow-sm'
            }`}>
              {msg.text}
            </div>
          </div>
        ))}
        {isLoading && (
           <div className="flex justify-start">
             <div className="bg-slate-800 p-3 rounded-lg border border-slate-700 shadow-sm rounded-bl-none flex items-center gap-2 text-slate-400 text-sm">
               <Loader2 size={16} className="animate-spin" />
               Calculating...
             </div>
           </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-slate-700 bg-slate-900">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Ask about opportunities..."
            className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 transition-colors"
          />
          <button 
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white p-2 rounded-lg transition-colors"
          >
            <Send size={18} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ChatBot;
