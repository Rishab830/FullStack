import React from "react";

function Header(props){
    return(
        <header className="header">
            <div className="logo">
                <a href="/">{props.siteName}</a>
            </div>
            <nav className="navigation">
                <a href="/home">Home</a>
                <a href="/about">About</a>
                <a href="/contact">Contact</a>
            </nav>
        </header>
    )
}

export default Header